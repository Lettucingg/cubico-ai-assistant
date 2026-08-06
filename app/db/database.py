from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

# El "engine" es el objeto que administra el pool de conexiones reales
# hacia PostgreSQL. Se crea UNA sola vez cuando arranca la aplicación,
# y se reutiliza durante toda la vida del servidor.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Verifica que la conexión siga viva antes de usarla
)

# SessionLocal es una "fábrica" de sesiones. Cada sesión representa
# una conversación individual y temporal con la base de datos:
# se abre, se hacen consultas, y se cierra. Nunca se comparte una
# sesión entre distintas peticiones al mismo tiempo.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base es la clase de la que van a heredar todos nuestros modelos
# (Cliente, Paquete, Factura...) en el archivo models.py.
# SQLAlchemy usa esto para saber qué clases de Python representan
# qué tablas de la base de datos.
Base = declarative_base()


def get_db():
    """
    Genera una sesión de base de datos para una sola petición HTTP,
    y garantiza que se cierre correctamente al terminar, incluso si
    ocurre un error en medio del proceso.

    FastAPI va a usar esta función como una "dependencia": cada vez
    que un endpoint necesite hablar con la base de datos, la recibe
    ya lista para usar, sin tener que abrir ni cerrar la conexión
    manualmente en cada lugar del código.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()