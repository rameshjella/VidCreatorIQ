from __future__ import annotations

import runpy
import sys
import os
from pathlib import Path


class _SafeFlushStream:
    def __init__(self, stream):
        self._stream = stream

    def flush(self):
        try:
            return self._stream.flush()
        except OSError:
            # Windows can raise OSError(22) on tqdm flush against redirected stderr.
            return None

    def __getattr__(self, name):
        return getattr(self._stream, name)


def main() -> None:
    # Launcher starts this script with cwd=ComfyUI, but absolute script execution can
    # remove cwd from import resolution on Windows.
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    os.environ.setdefault("TQDM_DISABLE", "1")
    sys.stderr = _SafeFlushStream(sys.stderr)

    # Rebuild argv so ComfyUI's argparse sees the same flags.
    sys.argv = ["main.py", *sys.argv[1:]]
    runpy.run_path("main.py", run_name="__main__")


if __name__ == "__main__":
    main()

