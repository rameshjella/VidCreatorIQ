"""Backwards-compatible shim.

The narration implementation now lives in
:mod:`app.services.narration_service` and is backed by the multi-provider
engine in :mod:`app.services.tts`.
"""

from app.services.narration_service import Narration, TTSService  # noqa: F401

__all__ = ["TTSService", "Narration"]

