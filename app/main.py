import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.music_routes import router as music_router
from app.api.routes import router
from app.database import Base, engine
from app.migrations import run_startup_migrations

run_startup_migrations(engine)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Movie Maker API", version="0.1.0")

allowed_origins_raw = os.getenv("UI_ALLOWED_ORIGINS", "").strip()
if allowed_origins_raw:
	allowed_origins = [item.strip() for item in allowed_origins_raw.split(",") if item.strip()]
else:
	allowed_origins = [
		"http://127.0.0.1:5173",
		"http://localhost:5173",
		"http://127.0.0.1:8501",
		"http://localhost:8501",
	]

app.add_middleware(
	CORSMiddleware,
	allow_origins=allowed_origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

app.include_router(router)
app.include_router(music_router)

