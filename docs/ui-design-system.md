# Web UI — Design System

## Theme

**Light is the default.** Dark is opt-in via the toggle in the top bar and
persists per browser in `localStorage` under `vidcreatoriq.theme`.

An inline script in `index.html` applies the stored theme *before first paint*,
so there is no flash of the wrong palette on reload.

```
:root                 → light palette
[data-theme="dark"]   → dark overrides
```

Every colour, space, radius, shadow and easing lives in
`ui/src/styles/tokens.css` and is declared exactly once. Components in
`ui/src/styles.css` reference tokens only — there are no hard-coded design
values, which is what lets a single attribute flip repaint the entire product
correctly.

### Palette rationale

Light surfaces climb toward pure white as elevation increases
(`--bg-base` #f6f7f9 → `--surface-1` #ffffff), with neutral-tinted shadows
rather than pure black so cards feel lifted instead of dirty. Status colours are
darkened in light mode (`--success` #0f8f4d) and brightened in dark mode
(#3ddc84) so both stay at AA contrast against their own background.

## Layout

```
┌──────────┬────────────────────────────────────┐
│ sidebar  │ topbar  (title · status · actions) │
│ 256px    ├────────────────────────────────────┤
│ grouped  │ content (max 1320px, centred)      │
│ nav      │                                    │
└──────────┴────────────────────────────────────┘
```

Below 900px the sidebar becomes an off-canvas drawer.

## Views

| View | Purpose |
|---|---|
| Script Studio | Hero, script editor, render settings, live word/runtime stats |
| Storyboard | Proportional timeline strip, per-scene cards, project library |
| Voice Studio | Engine picker, voice grid, instant MP3 preview |
| Music Studio | Prompt + presets, waveform, variations, generation history |
| Render Console | Weighted progress, stage stepper, streaming activity log |
| Preview & Export | Video player with captions, asset downloads, scene breakdown |
| System Health | Dependency status, narration engines, output profile |

**No view is gated.** Every screen is always reachable and renders a useful
empty state with a next action. Disabling navigation until data existed made
the product feel broken on first load, and hid the Storyboard entirely even
when finished projects were sitting in the database.

The Storyboard lists every past project and can reopen any of them via
`GET /projects/{id}/artifacts`, which resolves the project's most recent render
so the UI never has to track job IDs.

## Component discipline

`className` strings are invisible to TypeScript, so a component can silently
fall back to unstyled HTML if the stylesheet is refactored underneath it —
which is exactly how the Music Studio regressed. `tests/test_ui_classes.py`
extracts every class used in `.tsx` files and fails if the stylesheet does not
define it.

```
OK   App.tsx           96 classes
OK   ui.tsx            27 classes
OK   MusicStudio.tsx   45 classes
PASS - every class used in the UI is defined in the stylesheet.
```

## Layout safety

Grid children default to `min-width: auto`, which lets wide content push a
`1fr` column past its track and shove the top bar actions off-screen. `.main`,
`.content`, `.content__inner` and all `.grid > *` set `min-width: 0`, and grid
tracks use `minmax(min(320px, 100%), 1fr)` so nested grids shrink instead of
overflowing.

## Interaction

- **⌘K / Ctrl+K** opens a command palette with arrow-key navigation.
- Storyboard art appears **during** the render — job artifacts are polled every
  tick, not only on completion.
- Toasts announce job outcomes through an `aria-live="polite"` region.
- The activity log auto-scrolls like a build console.

## Accessibility

- Skip link to main content
- Visible focus ring on every interactive element (`--focus-ring`)
- `aria-current` on nav, `aria-pressed` on toggles, `role="log"` on the console
- Progress bars expose `aria-valuenow` / `min` / `max`
- All motion collapses under `prefers-reduced-motion: reduce`
- Captions track is attached to the video player by default

