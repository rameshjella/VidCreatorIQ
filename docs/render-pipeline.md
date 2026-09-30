# Render Pipeline & Voice Engine

## Why no video was being produced

The old pipeline failed silently at assembly. Five defects compounded:

1. **`concat -c copy` on video.** Clips were stream-copied together. Ken Burns
   clips, ComfyUI clips and placeholder clips all had different fps, SAR and
   timebases, so the concat demuxer produced corrupt or zero-length MP4s.
2. **`concat -c copy` on audio.** Piper emits 22.05 kHz, SAPI emits 48 kHz.
   Raw-copying PCM across those boundaries garbled the track.
3. **Clips had no audio stream.** `image_to_clip` produced video-only files, so
   stream layouts did not match during concat.
4. **`-c:s mov_text` + `-shortest` in the mux.** Embedding SRT into MP4 fails
   often, and `-shortest` truncated the movie to the silent video track.
5. **Nothing was ever verified.** No `ffprobe` call confirmed the output had
   streams, so failures surfaced as "completed" jobs with an unplayable file.

## How it works now

```
script → scenes → [per scene: TTS → measure duration → image → clip]
                → concat (re-encode) → mix audio → captions → master → verify
```

**Narration comes first.** Its *measured* duration becomes the scene duration,
so the picture can never drift out of sync with the audio. Previously the LLM's
guessed `duration_seconds` drove the clip length.

**Everything is normalised** to one canonical profile before concatenation
(`app/services/render_service.py`):

| Property | Value |
|---|---|
| Resolution | 1920×1080 (`RENDER_WIDTH`/`RENDER_HEIGHT`) |
| Frame rate | 30 fps, GOP 60 |
| Video | H.264, `yuv420p`, CRF 20, `+faststart` |
| Audio | AAC 192 kbps, 44.1 kHz, stereo |
| Loudness | −16 LUFS, −1.5 dBTP |

**Every output is validated** with `ffprobe` via
`app/services/ffmpeg_runner.py::validate_output`, which asserts non-zero
duration and the presence of the expected streams. A render can no longer
report success while producing a broken file.

**Graceful degradation where it is safe.** Crossfades fall back to hard cuts if
clips are too short; subtitle burn-in falls back to a clean mux if the font or
path resolution fails. Neither can block delivery of the movie.

### Timing detail

`xfade` overlaps neighbouring clips, so each clip except the last is rendered
`RENDER_TRANSITION_SECONDS` longer than its narration
(`MoviePipeline._clip_length`). Without this the picture ends up
`fade × (n−1)` seconds shorter than the audio.

## Voice engine

`app/services/tts/` replaces the previous 41-line pyttsx3 wrapper.

| Provider | Rank | Needs |
|---|---|---|
| ElevenLabs | 100 | `ELEVENLABS_API_KEY` |
| OpenAI | 90 | `OPENAI_API_KEY` |
| Azure Speech | 88 | `AZURE_SPEECH_KEY` + region |
| Google Cloud | 85 | `GOOGLE_APPLICATION_CREDENTIALS` |
| **Edge (default)** | 80 | nothing — free, neural |
| Piper | 60 | local binary + model |
| pyttsx3 | 10 | always available (safety net) |

Providers are attempted in `TTS_PROVIDER` order then `TTS_FALLBACK_CHAIN`;
unconfigured ones are skipped without cost. Each request is retried with
exponential backoff.

Output quality is now uniform regardless of source:

- long text split on sentence boundaries, rejoined with a configurable pause
- leading/trailing silence trimmed
- EBU R128 normalisation to −16 LUFS
- encoded to **MP3 192 kbps / 44.1 kHz** (previously raw WAV at whatever rate
  the engine happened to emit)
- results cached by `sha256(text + voice + provider + params)` so re-renders
  do not re-bill API calls

## Artifacts

The workspace is mounted at `/static/workspace`, so the UI previews media
directly instead of only offering a download. `GET /jobs/{id}/artifacts`
returns the final MP4, narration MP3, SRT, VTT, poster and every per-scene
image, clip and audio file as URLs.

## Verifying

```powershell
python scripts\smoketest_render.py   # services only, no server needed
python scripts\smoketest_api.py      # full stack; requires the API running
```

Both assert a real playable MP4 with both streams via `ffprobe`.

