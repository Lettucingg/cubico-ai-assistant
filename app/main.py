from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from app.api.whatsapp import router as whatsapp_router
from app.api.panel import router as panel_router
from app.api.notificaciones import router as notificaciones_router
from app.scheduler import iniciar_scheduler, scheduler

app = FastAPI(title="Cúbico AI Assistant")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(whatsapp_router)
app.include_router(panel_router)
app.include_router(notificaciones_router)

@app.get("/admin")
def panel_admin():
    return FileResponse(STATIC_DIR / "panel.html")

@app.on_event("startup")
def iniciar_tareas_programadas():
    iniciar_scheduler()

@app.on_event("shutdown")
def detener_tareas_programadas():
    scheduler.shutdown(wait=False)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Cúbico AI Assistant está vivo"}
