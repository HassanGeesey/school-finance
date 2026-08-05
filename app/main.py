"""FastAPI application factory.

The single entry point: creates the engine/session wiring, mounts static assets,
registers the base layout, and exposes the app. Feature routers are mounted here
as they land.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .db import Database, make_engine


def create_app(database_url: str | None = None) -> FastAPI:
    url = database_url or settings.DATABASE_URL

    # The default file-backed database needs its data directory to exist.
    if url == settings.DATABASE_URL:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    db = Database(make_engine(url))
    templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.create_all()
        yield

    app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)
    app.state.db = db

    app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context={
                "app_name": settings.APP_NAME,
                "app_version": settings.VERSION,
                "year": datetime.now(timezone.utc).year,
                "database_url": url,
            },
        )

    return app


app = create_app()
