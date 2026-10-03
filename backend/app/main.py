"""Point d'entrée FastAPI : API, diffusion des offres (plan du site, flux) et interface web."""
from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .config import get_settings
from .db import Base, get_db, get_engine
from .orchestrator import FlowError
from .routers import api, auth, public, webhooks
from .services import publication

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app() -> FastAPI:
    s = get_settings()
    if s.environment == "prod" and (s.secret_key.startswith("change-me") or len(s.secret_key) < 32):
        raise RuntimeError("SECRET_KEY doit être défini (32 caractères minimum) en production.")
    @asynccontextmanager
    async def lifespan(_: FastAPI):  # noqa: ANN202
        # Hébergement en un seul processus : refus programmés, relances, récapitulatifs, e-mails reçus.
        from . import scheduler

        scheduler.start()
        yield
        scheduler.stop()

    app = FastAPI(title=f"{s.app_name} — recrutement pour TPE et PME", version="0.4.0", lifespan=lifespan,
                  docs_url="/api/docs" if s.environment != "prod" else None, openapi_url="/api/openapi.json")

    if s.database_url.startswith("sqlite"):
        # En dev/test : création directe. En production (PostgreSQL) : migrations Alembic.
        from . import models  # noqa: F401

        Base.metadata.create_all(get_engine())

    if s.environment != "prod":
        app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                           allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # noqa: ANN001, ANN202
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        return resp

    @app.exception_handler(FlowError)
    async def flow_error(_: Request, exc: FlowError) -> JSONResponse:
        return JSONResponse({"detail": exc.message, **exc.extra}, status_code=exc.status)

    from .services.plans import PlanError

    @app.exception_handler(PlanError)
    async def plan_error(_: Request, exc: PlanError) -> JSONResponse:
        return JSONResponse({"detail": exc.message, "upgrade": True, "feature": exc.feature}, status_code=402)

    app.include_router(auth.router)
    app.include_router(api.router)
    app.include_router(public.router)
    app.include_router(webhooks.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    # --- Diffusion : robots, plan du site (Google pour l'emploi), flux des plateformes partenaires ---

    @app.get("/robots.txt", include_in_schema=False)
    def robots() -> PlainTextResponse:
        return PlainTextResponse(publication.robots_txt())

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap(db: Session = Depends(get_db)) -> Response:
        return Response(publication.sitemap_xml(db), media_type="application/xml",
                        headers={"Cache-Control": "public, max-age=900"})

    @app.get("/feeds/{partner}.xml", include_in_schema=False)
    def feed(partner: str, db: Session = Depends(get_db)) -> Response:
        if partner not in get_settings().publication_feeds:
            return JSONResponse({"detail": "Flux introuvable"}, status_code=404)
        return Response(publication.feed_xml(db, partner), media_type="application/xml",
                        headers={"Cache-Control": "public, max-age=900"})

    static_dir = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
        index_html = static_dir / "index.html"

        @app.get("/offres/{token}", include_in_schema=False)
        def offer_page(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
            """Page publique d'une offre, servie avec ses balises et ses données structurées JobPosting."""
            page = index_html.read_text(encoding="utf-8")
            head = publication.page_head(db, token)
            if head:
                page = re.sub(r"<title>.*?</title>", lambda _: head, page, count=1, flags=re.S)
            return HTMLResponse(page, headers={"Cache-Control": "no-cache"})

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith(("api/", "webhooks/", "feeds/")):
                return JSONResponse({"detail": "Introuvable"}, status_code=404)  # type: ignore[return-value]
            candidate = static_dir / path
            if path and candidate.is_file() and static_dir in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(index_html, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
