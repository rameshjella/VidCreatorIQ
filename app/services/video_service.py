"""Backwards-compatible shim.

The rendering implementation now lives in :mod:`app.services.render_service`.
"""

from app.services.render_service import RenderService, VideoService, _escape_filter_path  # noqa: F401

__all__ = ["RenderService", "VideoService"]

