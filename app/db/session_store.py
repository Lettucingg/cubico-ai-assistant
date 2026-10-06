import json

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings

ZONA_PANAMA = ZoneInfo("America/Panama")

_session_database_url = settings.SESSION_DATABASE_URL
_engine_options = {"pool_pre_ping": True}
if _session_database_url.startswith("sqlite"):
    _engine_options["connect_args"] = {"check_same_thread": False}

engine_sesiones = create_engine(_session_database_url, **_engine_options)
SessionSesiones = sessionmaker(bind=engine_sesiones)
BaseSesiones = declarative_base()


class Sesion(BaseSesiones):
    """
    Representa el estado de la conversación con un número de
    teléfono específico, incluyendo el historial de mensajes
    recientes para que Claude tenga memoria de la conversación.
    """
    __tablename__ = "sesiones"

    id = Column(Integer, primary_key=True)
    telefono = Column(String, unique=True, nullable=False)
    estado = Column(String, default="esperando_codigo")
    codigo_cliente_temporal = Column(String, nullable=True)
    codigo_cliente_verificado = Column(String, nullable=True)
    tipo_cliente_verificado = Column(String, nullable=True)  # cbc | agencia
    historial_json = Column(Text, default="[]")
    necesita_atencion_humana = Column(Boolean, default=False)
    motivo_escalamiento = Column(Text, nullable=True)
    aviso_retiro_pendiente = Column(Boolean, default=False)
    paquetes_a_retirar = Column(Text, nullable=True)
    solicitud_domicilio_pendiente = Column(Boolean, default=False)
    direccion_domicilio = Column(Text, nullable=True)
    paquetes_a_domicilio = Column(Text, nullable=True)
    factura_pendiente_notificacion = Column(String, nullable=True)
    tipo_seguimiento_pago = Column(String, nullable=True)  # general | domicilio
    actualizado_en = Column(DateTime, default=datetime.utcnow)
    ultimo_leido_panel = Column(DateTime, nullable=True)
    atencion_humana_directa = Column(Boolean, default=False)
    atencion_humana_por = Column(String, nullable=True)
    atencion_humana_desde = Column(DateTime, nullable=True)
    pago_reportado = Column(Boolean, default=False)
    pago_confirmado = Column(Boolean, default=False)
    paquetes_preparados = Column(Boolean, default=False)
    domicilio_coordinado = Column(Boolean, default=False)
    entregado = Column(Boolean, default=False)
    metodo_pago_reportado = Column(String, nullable=True)
    monto_pago_reportado = Column(Float, nullable=True)
    referencia_pago_reportado = Column(String, nullable=True)
    fecha_pago_reportado = Column(String, nullable=True)
    comprobante_media_id = Column(String, nullable=True)
    revisiones_comprobante_json = Column(Text, nullable=True)
    solicitud_actualizada_en = Column(DateTime, nullable=True)

    def obtener_historial(self):
        """Convierte el historial guardado (texto JSON) en una lista de Python."""
        return json.loads(self.historial_json or "[]")


class UsoIA(BaseSesiones):
    """Una fila por llamada a Claude para medir consumo y costo por chat."""

    __tablename__ = "uso_ia"

    id = Column(Integer, primary_key=True)
    telefono = Column(String, index=True, nullable=False)
    modelo = Column(String, nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    costo_usd = Column(Float, default=0.0, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)


class SuscripcionPush(BaseSesiones):
    """Dispositivo autorizado para recibir avisos del panel."""

    __tablename__ = "suscripciones_push"

    id = Column(Integer, primary_key=True)
    endpoint = Column(Text, unique=True, nullable=False)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    usuario = Column(String, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    actualizado_en = Column(DateTime, default=datetime.utcnow, nullable=False)


class OportunidadComercial(BaseSesiones):
    """Posible cliente empresarial identificado durante una conversación."""

    __tablename__ = "oportunidades_comerciales"

    id = Column(Integer, primary_key=True)
    telefono = Column(String, index=True, nullable=False)
    estado = Column(String, default="nueva", index=True, nullable=False)
    empresa = Column(String, nullable=True)
    nombre_contacto = Column(String, nullable=True)
    cargo_contacto = Column(String, nullable=True)
    necesidad = Column(Text, nullable=True)
    mercancia = Column(Text, nullable=True)
    origen = Column(String, nullable=True)
    proveedores_actuales = Column(Text, nullable=True)
    volumen_estimado = Column(Text, nullable=True)
    frecuencia = Column(Text, nullable=True)
    modalidades = Column(Text, nullable=True)
    urgencia = Column(Text, nullable=True)
    preferencia_entrega = Column(Text, nullable=True)
    direccion_entrega = Column(Text, nullable=True)
    condiciones = Column(Text, nullable=True)
    asignado_a = Column(String, nullable=True)
    notas_internas = Column(Text, nullable=True)
    creada_en = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    actualizada_en = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    cerrada_en = Column(DateTime, nullable=True)


class InformeDiario(BaseSesiones):
    __tablename__ = "informes_diarios"

    id = Column(Integer, primary_key=True)
    clave = Column(String, unique=True, nullable=False)
    tipo = Column(String, nullable=False)
    contenido = Column(Text, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)


class AlertaArchivada(BaseSesiones):
    __tablename__ = "alertas_archivadas"

    id = Column(Integer, primary_key=True)
    firma = Column(String(64), unique=True, nullable=False)
    clave = Column(Text, nullable=False)
    titulo = Column(Text, nullable=False)
    descripcion = Column(Text, nullable=False)
    motivo = Column(String(20), nullable=False)
    usuario = Column(String, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)


class PerfilPanel(BaseSesiones):
    __tablename__ = "perfiles_panel"
    usuario = Column(String, primary_key=True)
    nombre = Column(String(80), nullable=True)
    foto = Column(Text, nullable=True)
    contrasena_hash = Column(Text, nullable=True)


class PreferenciasAvisos(BaseSesiones):
    __tablename__ = "preferencias_avisos_panel"
    usuario = Column(String, primary_key=True)
    categoria = Column(String, nullable=False, default="ambos")


class TrackingVigilado(BaseSesiones):
    __tablename__ = "tracking_vigilado"
    tracking = Column(String, primary_key=True)
    telefono = Column(String, primary_key=True)
    ingreso_miami = Column(DateTime, nullable=True)
    push_demora = Column(Boolean, default=False)
    push_malid = Column(Boolean, default=False)
    demora = Column(Boolean, default=False)
    mal_identificado = Column(Boolean, default=False)
    actualizado_en = Column(DateTime, default=datetime.utcnow)


class EnvioPanelUnico(BaseSesiones):
    __tablename__ = "envios_panel_unicos"
    clave = Column(String(64), primary_key=True)
    contenido_hash = Column(String(64), nullable=False)
    resultado = Column(Text, nullable=True)


BaseSesiones.metadata.create_all(engine_sesiones)


def _migrar_columnas_faltantes():
    """
    create_all() no agrega columnas nuevas a una tabla que ya existe.
    Si sesiones.db viene de una versión anterior del modelo, esto agrega
    cualquier columna que falte sin tocar los datos existentes.
    """
    columnas_existentes = {
        col["name"] for col in inspect(engine_sesiones).get_columns("sesiones")
    }
    faltantes = [c for c in Sesion.__table__.columns if c.name not in columnas_existentes]
    if not faltantes:
        return
    with engine_sesiones.begin() as conexion:
        for columna in faltantes:
            tipo_sql = columna.type.compile(engine_sesiones.dialect)
            conexion.execute(text(f"ALTER TABLE sesiones ADD COLUMN {columna.name} {tipo_sql}"))


_migrar_columnas_faltantes()


ESTADOS_OPORTUNIDAD = {
    "nueva",
    "en_revision",
    "preparando_propuesta",
    "propuesta_enviada",
    "seguimiento",
    "ganada",
    "no_concretada",
}

CAMPOS_OPORTUNIDAD_EDITABLES = {
    "empresa",
    "nombre_contacto",
    "cargo_contacto",
    "necesidad",
    "mercancia",
    "origen",
    "proveedores_actuales",
    "volumen_estimado",
    "frecuencia",
    "modalidades",
    "urgencia",
    "preferencia_entrega",
    "direccion_entrega",
    "condiciones",
}


def _texto_limpio(valor, limite: int = 1200) -> str | None:
    if valor is None:
        return None
    limpio = " ".join(str(valor).split()).strip()
    return limpio[:limite] if limpio else None


def _resumen_oportunidad(registro: OportunidadComercial) -> str:
    sujeto = registro.empresa or registro.nombre_contacto or "Este posible cliente empresarial"
    partes = []
    if registro.necesidad:
        partes.append(f"necesita {registro.necesidad.rstrip('.')}" )
    if registro.mercancia:
        origen = f" desde {registro.origen}" if registro.origen else ""
        partes.append(f"maneja {registro.mercancia.rstrip('.')}{origen}")
    if registro.volumen_estimado or registro.frecuencia:
        volumen = registro.volumen_estimado or "volumen aún por confirmar"
        frecuencia = f" ({registro.frecuencia})" if registro.frecuencia else ""
        partes.append(f"reporta {volumen}{frecuencia}")
    if registro.modalidades:
        partes.append(f"le interesa {registro.modalidades.rstrip('.')}")
    if registro.preferencia_entrega:
        partes.append(f"prefiere {registro.preferencia_entrega.rstrip('.')}")
    if registro.proveedores_actuales:
        partes.append(f"actualmente trabaja con {registro.proveedores_actuales.rstrip('.')}")
    if not partes:
        return f"{sujeto} mostró interés en una tarifa o servicio empresarial."
    return f"{sujeto} " + "; ".join(partes) + "."


def _faltantes_oportunidad(registro: OportunidadComercial) -> list[str]:
    etiquetas = {
        "empresa": "nombre de la empresa",
        "nombre_contacto": "nombre de la persona de contacto",
        "mercancia": "tipo de mercancía",
        "volumen_estimado": "volumen aproximado",
        "modalidades": "modalidad de envío",
        "preferencia_entrega": "forma de entrega o retiro",
    }
    return [etiqueta for campo, etiqueta in etiquetas.items() if not getattr(registro, campo)]


def _oportunidad_dict(registro: OportunidadComercial) -> dict:
    return {
        "id": registro.id,
        "codigo": f"OP-{registro.id:04d}",
        "telefono": registro.telefono,
        "estado": registro.estado,
        "empresa": registro.empresa,
        "nombre_contacto": registro.nombre_contacto,
        "cargo_contacto": registro.cargo_contacto,
        "necesidad": registro.necesidad,
        "mercancia": registro.mercancia,
        "origen": registro.origen,
        "proveedores_actuales": registro.proveedores_actuales,
        "volumen_estimado": registro.volumen_estimado,
        "frecuencia": registro.frecuencia,
        "modalidades": registro.modalidades,
        "urgencia": registro.urgencia,
        "preferencia_entrega": registro.preferencia_entrega,
        "direccion_entrega": registro.direccion_entrega,
        "condiciones": registro.condiciones,
        "asignado_a": registro.asignado_a,
        …8758 tokens truncated…,'Nuevo mensaje · '+name,c.ultimo_mensaje_cliente?.contenido||'Mensaje pendiente',target,true);
      if(c.ultimo_mensaje?.estado_entrega==='failed')add('fallido',c.telefono,[message(c.ultimo_mensaje),text(c.ultimo_mensaje.error_entrega)],'Mensaje no entregado · '+name,c.ultimo_mensaje.error_entrega||'Meta rechazó el último envío',target);
    });
    solicitudes.forEach(s=>{
      const target={view:'packages',tel:s.telefono,type:s.tipo},version=[text(s.actualizado_en),s.monto_reportado??null,!!s.tiene_comprobante,text(s.referencia_pago)];
      if(s.pago_reportado&&!s.pago_confirmado)add('pago',s.telefono+':'+s.tipo,version,(s.tiene_comprobante?'Comprobante por revisar':'Pago por comprobar')+' · '+s.nombre,s.monto_reportado==null?'Monto pendiente de completar':'Monto reportado: $'+Number(s.monto_reportado).toFixed(2),target,true);
      if(s.tipo==='domicilio'&&(!s.direccion||s.direccion==='—'))add('direccion',s.telefono+':'+s.tipo,[text(s.actualizado_en)],'Domicilio sin dirección · '+s.nombre,'Falta confirmar la dirección exacta del cliente.',target);
    });
    oportunidades.filter(o=>o.estado==='nueva').forEach(o=>add('oportunidad',o.id,[text(o.actualizada_en||o.creada_en)],'Nueva oportunidad · '+(o.empresa||o.nombre_contacto||o.telefono),o.resumen||'Posible cliente empresarial',{view:'opportunities',id:o.id},true));
    return rows;
  }
  const groups={humano:'equipo',mensaje:'equipo',fallido:'equipo',pago:'pagos',direccion:'operaciones',malid:'equipo',demora_miami:'equipo',oportunidad:'negocios'};
  const labels={equipo:'Atención del equipo',pagos:'Pagos por revisar',operaciones:'Retiros y domicilios',negocios:'Negocios'};
  function filter(rows,search='',group='all'){
    const query=search.trim().toLocaleLowerCase('es');
    return rows.filter(a=>(group==='all'||groups[a.kind]===group)&&(!query||(a.titulo+' '+a.descripcion).toLocaleLowerCase('es').includes(query)));
  }
  root.CubicoAlerts={collect,filter,groups,labels};
  if(typeof module!=='undefined')module.exports=root.CubicoAlerts;
})(typeof window!=='undefined'?window:globalThis);
