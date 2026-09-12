from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Configuración central del proyecto Cúbico AI Assistant.

    Cada atributo de esta clase representa una variable de entorno
    que el sistema necesita para funcionar. Pydantic se encarga de:
      - Leerlas automáticamente desde el archivo .env
      - Validar que existan y tengan el tipo correcto
      - Fallar de inmediato con un error claro si falta alguna
    """

    # --- Base de datos ---
    DATABASE_URL: str

    # --- Anthropic (Claude API) ---
    ANTHROPIC_API_KEY: str

    # --- WhatsApp Cloud API (Meta) ---
    WHATSAPP_TOKEN: str
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_VERIFY_TOKEN: str
    #--- OpenAI (ChatGPT API) ---
    OPENAI_API_KEY: str

    # --- Panel de administración (HTTP Basic Auth) ---
    # JSON con los usuarios del panel, ej: {"alexander":"...","luis":"..."}
    # Nunca hardcodear usuarios/contraseñas en el código.
    PANEL_USUARIOS_JSON: str

    # --- Notificaciones internas (POST /notificar/carga-llegada) ---
    # Clave compartida esperada en el header X-Cubico-Key.
    CUBICO_NOTIFY_KEY: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Instancia única y reutilizable en todo el proyecto.
# En vez de crear Settings() en cada archivo, todos importan esta misma variable.
settings = Settings()
