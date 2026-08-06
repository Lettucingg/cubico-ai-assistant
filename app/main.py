from fastapi import FastAPI
from app.core.config import settings
from app.api.whatsapp import router as whatsapp_router

app = FastAPI(title="Cúbico AI Assistant")

app.include_router(whatsapp_router)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Cúbico AI Assistant está vivo"}


@app.get("/debug/config")
def debug_config():
    return {
        "database_url_cargada": settings.DATABASE_URL[:20] + "...",
        "whatsapp_verify_token": settings.WHATSAPP_VERIFY_TOKEN,
    }