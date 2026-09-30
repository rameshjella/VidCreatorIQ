"""Guard against components drifting off the design system.

The Music Studio regressed to raw unstyled HTML because it kept referencing
class names (``pillRow``, ``exampleChip``, ``.primary``, ``.help``) that were
removed when the stylesheet was rewritten. Nothing caught it because TypeScript
does not type-check ``className`` strings.

This test extracts every class used in the app and asserts the stylesheet
defines it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

UI_SRC = Path(__file__).resolve().parents[1] / "ui" / "src"

# Classes applied dynamically or supplied by third parties.
IGNORED = {"dist"}


def defined_classes() -> set[str]:
    css = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [UI_SRC / "styles.css", UI_SRC / "styles" / "tokens.css"]
    )
    # Strip comments so commented-out rules do not count as defined.
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return set(re.findall(r"\.([a-zA-Z][\w-]*)", css))


def used_classes() -> dict[str, set[str]]:
    usage: dict[str, set[str]] = {}
    for path in sorted(UI_SRC.rglob("*.tsx")):
        source = path.read_text(encoding="utf-8")
        found: set[str] = set()
        # className="a b c"  and  className={"a b" ...}
        for match in re.findall(r'className=(?:\{)?["`\']([^"`\']+)["`\']', source):
            for token in match.split():
                if "${" in token or "{" in token:
                    continue
                found.add(token)
        if found:
            usage[path.name] = found
    return usage


def main() -> int:
    defined = defined_classes()
    usage = used_classes()

    missing_total = 0
    for filename, classes in usage.items():
        missing = sorted(c for c in classes if c not in defined and c not in IGNORED)
        status = "OK  " if not missing else "FAIL"
        print(f"  {status} {filename:<22} {len(classes)} classes")
        for name in missing:
            print(f"         undefined: .{name}")
        missing_total += len(missing)

    if missing_total:
        print(f"\nFAIL - {missing_total} class(es) used but never defined.")
        return 1
    print("\nPASS - every class used in the UI is defined in the stylesheet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

