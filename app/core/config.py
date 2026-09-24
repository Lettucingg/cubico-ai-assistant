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
    # Conversaciones del panel. Si no se define, mantiene el SQLite actual.
    # En Railway debe apuntar a PostgreSQL o a un volumen persistente.
    SESSION_DATABASE_URL: str = "sqlite:///sesiones.db"

    # Precios configurables para calcular el costo real de Claude. Se guardan
    # con cada llamada, de modo que cambiar la tarifa no altera el histórico.
    ANTHROPIC_INPUT_USD_PER_MTOK: float = 3.0
    ANTHROPIC_OUTPUT_USD_PER_MTOK: float = 15.0

    # --- Anthropic (Claude API) ---
    ANTHROPIC_API_KEY: str

    # --- WhatsApp Cloud API (Meta) ---
    WHATSAPP_TOKEN: str
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_VERIFY_TOKEN: str
    # Plantillas aprobadas en Meta. El idioma debe coincidir exactamente con
    # la traducción aprobada (por ejemplo, Spanish (PAN) usa es_PA).
    WHATSAPP_TEMPLATE_SALUDO_NAME: str = "cubico_saludo"
    WHATSAPP_TEMPLATE_SALUDO_LANGUAGE: str = "es_PA"
    WHATSAPP_TEMPLATE_PROPUESTA_NAME: str = "cubico_propuesta"
    WHATSAPP_TEMPLATE_PROPUESTA_LANGUAGE: str = "es"
    #--- OpenAI (ChatGPT API) ---
    OPENAI_API_KEY: str

    # --- Panel de administración (HTTP Basic Auth) ---
    # JSON con los usuarios del panel, ej: {"alexander":"...","luis":"..."}
    # Nunca hardcodear usuarios/contraseñas en el código.
    PANEL_USUARIOS_JSON: str

    # --- Notificaciones push del panel instalable ---
    # La clave privada permanece únicamente en el VPS. La pública se entrega
    # al navegador para crear la suscripción Web Push.
    PUSH_VAPID_PRIVATE_KEY_PATH: str = "vapid_private.pem"
    PUSH_VAPID_PUBLIC_KEY: str = ""
    PUSH_VAPID_SUBJECT: str = "mailto:soporte@cubico.com.pa"

    # --- Notificaciones internas (POST /notificar/carga-llegada) ---
    # Clave compartida esperada en el header X-Cubico-Key.
    CUBICO_NOTIFY_KEY: str

    # --- Datos privados del negocio (no publicar en GitHub) ---
    CUBICO_TEAM_COMMAND_NUMBERS_JSON: str = "[]"
    CUBICO_NOTIFICATION_NUMBERS_JSON: str = "[]"
    # ID de un grupo creado con la API oficial de grupos de WhatsApp.
    # Un enlace de invitación o el nombre de un grupo normal no sirve aquí.
    CUBICO_TEAM_REPORT_GROUP_ID: str = ""
    CUBICO_TEAM_REPORT_TEMPLATE: str = ""
    CUBICO_TEAM_REPORT_TEMPLATE_LANGUAGE: str = "es"
    CUBICO_PAYMENT_ACCOUNT: str = ""
    CUBICO_PAYMENT_YAPPY: str = ""
    CUBICO_MIAMI_STREET: str = ""
    CUBICO_MIAMI_CITY_ZIP: str = ""
    CUBICO_MIAMI_PHONE: str = ""
    CUBICO_CHINA_AIR_ADDRESS: str = ""
    CUBICO_CHINA_AIR_PHONE: str = ""
    CUBICO_CHINA_OCEAN_ADDRESS: str = ""
    CUBICO_CHINA_OCEAN_ROUTE_CODE: str = ""
    CUBICO_CHINA_OCEAN_PHONE_PRIMARY: str = ""
    CUBICO_CHINA_OCEAN_PHONE_SECONDARY: str = ""
    CUBICO_LOCAL_ADDRESS: str = ""
    CUBICO_LOCAL_PHONE: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Instancia única y reutilizable en todo el proyecto.
# En vez de crear Settings() en cada archivo, todos importan esta misma variable.
settings = Settings()
