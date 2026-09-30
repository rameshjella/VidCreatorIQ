import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.music_routes import router as music_router
from app.api.routes import router
from app.api.tts_routes import router as tts_router
from app.config import settings
from app.database import Base, engine
from app.migrations import run_startup_migrations
from app.win_asyncio_patch import install as install_win_asyncio_patch

# Silence benign WinError 10054 tracebacks from browser disconnects.
install_win_asyncio_patch()

run_startup_migrations(engine)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Movie Maker API", version="0.1.0")

# Ports the dev/prod UI is commonly served from. The launcher uses 8501, Vite's
# own default is 5173, and `vite preview` uses 4173.
_DEFAULT_UI_PORTS = (8501, 5173, 4173, 3000)
_DEFAULT_ORIGINS = [
	f"http://{host}:{port}"
	for port in _DEFAULT_UI_PORTS
	for host in ("127.0.0.1", "localhost")
]

# Anything configured in .env is *added to* the defaults rather than replacing
# them. Previously setting UI_ALLOWED_ORIGINS to the Vite default silently
# blocked the launcher's 8501 origin, so every CORS preflight returned 400.
allowed_origins_raw = os.getenv("UI_ALLOWED_ORIGINS", "").strip()
configured_origins = [item.strip().rstrip("/") for item in allowed_origins_raw.split(",") if item.strip()]
allowed_origins = list(dict.fromkeys([*_DEFAULT_ORIGINS, *configured_origins]))

app.add_middleware(
	CORSMiddleware,
	allow_origins=allowed_origins,
	# Covers any other localhost port the UI might be started on.
	allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
	expose_headers=["Content-Length", "Content-Range", "Content-Disposition"],
)

app.include_router(router)
app.include_router(music_router)
app.include_router(tts_router)

# Serve render artifacts (images, clips, MP3s, captions, the final MP4) so the
# web UI can preview them directly instead of only offering a download.
settings.workspace_dir.mkdir(parents=True, exist_ok=True)
app.mount(
	"/static/workspace",
	StaticFiles(directory=str(settings.workspace_dir)),
	name="workspace",
)
