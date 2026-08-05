from fastapi import FastAPI
from app.core.config import settings

app = FastAPI(title="Cúbico AI Assistant")


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Cúbico AI Assistant está vivo"}


@app.get("/debug/config")
def debug_config():
    """
    Endpoint TEMPORAL solo para confirmar que la configuración carga bien.
    Lo vamos a eliminar antes de llegar a producción — nunca se debe
    exponer configuración real en un endpoint público.
    """
    return {
        "database_url_cargada": settings.DATABASE_URL[:20] + "...",
        "whatsapp_verify_token": settings.WHATSAPP_VERIFY_TOKEN,
    }