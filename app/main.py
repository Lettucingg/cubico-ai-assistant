from fastapi import FastAPI
from app.api.whatsapp import router as whatsapp_router

app = FastAPI(title="Cúbico AI Assistant")

app.include_router(whatsapp_router)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Cúbico AI Assistant está vivo"}