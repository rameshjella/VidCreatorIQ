"""Windows-specific asyncio noise suppression.

On Windows the Proactor event loop raises ``ConnectionResetError`` (WinError
10054) from ``_call_connection_lost`` whenever a browser closes a keep-alive
socket early — which happens constantly with polling UIs and media elements
that abort range requests.

The exception is entirely benign (the connection is already gone; the code is
merely trying to shut down the socket), but asyncio surfaces it through the
loop's exception handler, which floods the logs with tracebacks and hides real
errors. This patch swallows only that specific case.
"""

from __future__ import annotations

import sys


def install() -> None:
    if not sys.platform.startswith("win"):
        return

    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport
    except ImportError:  # pragma: no cover - non-CPython or future refactor
        return

    original = _ProactorBasePipeTransport._call_connection_lost
    if getattr(original, "__vidcreatoriq_patched__", False):
        return

    def _quiet_call_connection_lost(self, exc):  # type: ignore[no-untyped-def]
        try:
            original(self, exc)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # The peer already vanished; nothing to clean up and nothing to report.
            pass

    _quiet_call_connection_lost.__vidcreatoriq_patched__ = True  # type: ignore[attr-defined]
    _ProactorBasePipeTransport._call_connection_lost = _quiet_call_connection_lost  # type: ignore[method-assign]

