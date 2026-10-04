from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.services import narration_service
from app.services.narration_service import TTSService
from app.services.tts.base import TTSPermanentFailure, TTSResult, TTSUnavailable
from app.services.tts.openai_provider import OpenAITTSProvider


def test_openai_provider_marks_quota_exhaustion_as_permanent(monkeypatch) -> None:
    provider = OpenAITTSProvider()
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "openai_base_url", "https://api.openai.com/v1")

    def _fake_post(*_args, **_kwargs):
        req = httpx.Request("POST", "https://api.openai.com/v1/audio/speech")
        return httpx.Response(
            429,
            request=req,
            text=(
                '{"error":{"message":"no credits","type":"insufficient_quota",'
                '"code":"credit_balance_exhausted"}}'
            ),
        )

    monkeypatch.setattr(httpx, "post", _fake_post)

    with pytest.raises(TTSPermanentFailure, match="credits are exhausted"):
        provider.synthesize("hello world")


def test_tts_service_disables_provider_after_permanent_failure(monkeypatch, tmp_path: Path) -> None:
    class _AlwaysPermanentFailProvider:
        name = "openai"

        def __init__(self):
            self.calls = 0

        def synthesize(self, *_args, **_kwargs):
            self.calls += 1
            raise TTSPermanentFailure("credits are exhausted")

    provider = _AlwaysPermanentFailProvider()
    monkeypatch.setattr(narration_service, "resolve_provider_chain", lambda _preferred: [provider])

    service = TTSService(tmp_path / "audio")

    with pytest.raises(TTSUnavailable):
        service.synthesize_detailed("scene one", 1)
    assert provider.calls == 1

    with pytest.raises(TTSUnavailable):
        service.synthesize_detailed("scene two", 2)
    assert provider.calls == 1


def test_tts_service_emits_openai_quota_fallback_notice(monkeypatch, tmp_path: Path) -> None:
    class _OpenAIFailProvider:
        name = "openai"

        def synthesize(self, *_args, **_kwargs):
            raise TTSPermanentFailure("credits are exhausted")

    class _EdgeSuccessProvider:
        name = "edge"

        def synthesize(self, *_args, **_kwargs):
            return TTSResult(audio=b"dummy", source_format="mp3", provider=self.name, voice="edge-voice")

    def _fake_concat_segments(_segments, output_path):
        out = Path(output_path)
        out.write_bytes(b"ok")
        return out

    monkeypatch.setattr(
        narration_service,
        "resolve_provider_chain",
        lambda _preferred: [_OpenAIFailProvider(), _EdgeSuccessProvider()],
    )
    monkeypatch.setattr(narration_service.postprocess, "split_sentences", lambda _text: ["hello"])
    monkeypatch.setattr(
        narration_service.postprocess,
        "encode_to_mp3",
        lambda _audio, _source_format, out_path: Path(out_path).write_bytes(b"ok") or Path(out_path),
    )
    monkeypatch.setattr(
        narration_service.postprocess,
        "concat_segments",
        _fake_concat_segments,
    )
    monkeypatch.setattr(narration_service.ff, "probe_duration", lambda _path: 1.2)

    service = TTSService(tmp_path / "audio")
    result = service.synthesize_detailed("scene one", 1)

    assert result.provider == "edge"
    assert "OpenAI credits exhausted, switched to fallback provider" in result.notices


