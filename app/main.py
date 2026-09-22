from fastapi import FastAPI

from app.api.routes import router
from app.database import Base, engine
from app.migrations import run_startup_migrations

run_startup_migrations(engine)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Movie Maker API", version="0.1.0")
app.include_router(router)

