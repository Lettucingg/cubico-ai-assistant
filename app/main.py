from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from app.api.whatsapp import router as whatsapp_router
from app.api.panel import router as panel_router
from app.api.notificaciones import router as notificaciones_router
from app.scheduler import iniciar_scheduler, scheduler

from contextlib import asynccontextmanager
from app.api.staff_mcp import mcp, mcp_app


@asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        iniciar_scheduler()
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)


app = FastAPI(title="Cúbico AI Assistant", lifespan=lifespan)
from app.api.staff_oauth import oauth_app, metadata as oauth_metadata, resource_metadata
from starlette.routing import Route
app.mount('/panel/ia/oauth', oauth_app)
# RFC 8414/9728 discovery aliases, including path-specific authorization-server metadata.
app.router.routes.extend([
    Route('/.well-known/oauth-authorization-server/panel/ia/oauth', oauth_metadata),
    Route('/.well-known/oauth-authorization-server', oauth_metadata),
    Route('/.well-known/oauth-protected-resource/mcp', resource_metadata),
    Route('/.well-known/oauth-protected-resource/mcp/', resource_metadata),
])
app.mount('/mcp', mcp_app)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(whatsapp_router)
app.include_router(panel_router)
app.include_router(notificaciones_router)

@app.get("/admin")
def panel_admin():
    return FileResponse(STATIC_DIR / "panel-nuevo-diseno.html")


@app.get("/admin-anterior")
def panel_admin_anterior():
    """Respaldo inmediato del panel anterior durante la transición."""
    return FileResponse(STATIC_DIR / "panel.html")


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest_panel():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/service-worker.js", include_in_schema=False)
def service_worker_panel():
    return FileResponse(
        STATIC_DIR / "service-worker.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Cúbico AI Assistant está vivo"}
