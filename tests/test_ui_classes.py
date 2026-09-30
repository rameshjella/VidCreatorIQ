"""Guard against UI components drifting off the design system.

The Music Studio silently regressed to unstyled HTML because it kept using
class names (``pillRow``, ``exampleChip``, ``.primary``, ``.help``) that were
removed when the stylesheet was rewritten. TypeScript does not type-check
``className`` strings, so the build stayed green while the page looked broken.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

UI_SRC = Path(__file__).resolve().parents[1] / "ui" / "src"
STYLESHEETS = [UI_SRC / "styles.css", UI_SRC / "styles" / "tokens.css"]

TSX_FILES = sorted(UI_SRC.rglob("*.tsx")) if UI_SRC.exists() else []


def _defined_classes() -> set[str]:
    css = "\n".join(path.read_text(encoding="utf-8") for path in STYLESHEETS)
    # Strip comments so commented-out rules do not count as defined.
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return set(re.findall(r"\.([a-zA-Z][\w-]*)", css))


def _used_classes(source: str) -> set[str]:
    found: set[str] = set()
    for match in re.findall(r'className=(?:\{)?["`\']([^"`\']+)["`\']', source):
        for token in match.split():
            if "${" in token or "{" in token:
                continue  # interpolated at runtime
            found.add(token)
    return found


@pytest.mark.skipif(not TSX_FILES, reason="UI sources not present")
@pytest.mark.parametrize("tsx", TSX_FILES, ids=lambda p: p.name)
def test_every_class_is_defined(tsx: Path) -> None:
    defined = _defined_classes()
    used = _used_classes(tsx.read_text(encoding="utf-8"))
    undefined = sorted(name for name in used if name not in defined)
    assert not undefined, (
        f"{tsx.name} uses classes with no CSS rule: {', '.join(undefined)}. "
        "The component will render unstyled."
    )


@pytest.mark.skipif(not STYLESHEETS[0].exists(), reason="stylesheet not present")
def test_component_layer_uses_tokens_not_raw_colours() -> None:
    """Hard-coded colours break theming, since only tokens flip with data-theme."""
    css = STYLESHEETS[0].read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

    offenders: list[str] = []
    for line in css.splitlines():
        if "--" in line or "rgba(8, 8, 10" in line:
            continue  # token definitions and deliberate media overlays
        if re.search(r":\s*#[0-9a-fA-F]{3,8}\b", line) and "#fff" not in line and "#000" not in line:
            offenders.append(line.strip())

    assert not offenders, "Use tokens instead of literal colours:\n" + "\n".join(offenders)

