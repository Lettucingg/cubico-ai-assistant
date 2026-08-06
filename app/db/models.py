from sqlalchemy import Column, Integer, String, Numeric, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship

from app.db.database import Base


class ClienteCBC(Base):
    """
    Representa un cliente final (persona natural) de Cúbico.
    Mapea directamente a la tabla 'clientes_cbc' que ya existe
    en la base de datos de producción.
    """
    __tablename__ = "clientes_cbc"

    id = Column(Integer, primary_key=True)
    codigo = Column(String, unique=True, nullable=False)  # Ej: CBC-0001
    numero = Column(String)
    nombre = Column(String, nullable=False)
    apellido = Column(String)
    email = Column(String)
    telefono = Column(String)
    cedula = Column(String)
    direccion = Column(String)
    modalidad = Column(String)
    password_hash = Column(String)
    tarifa_aerea = Column(Numeric)
    tarifa_maritima = Column(Numeric)
    tarifa_china_aerea = Column(Numeric)
    tarifa_china_maritima = Column(Numeric)
    activo = Column(Boolean, default=True)

    paquetes = relationship("Paquete", back_populates="cliente_cbc")
    facturas = relationship("Factura", back_populates="cliente_cbc")
    pagos = relationship("Pago", back_populates="cliente_cbc")


class Agencia(Base):
    """
    Representa una agencia/revendedor (cliente tipo empresa).
    Mapea a la tabla 'agencias'.
    """
    __tablename__ = "agencias"

    id = Column(Integer, primary_key=True)
    codigo = Column(String, unique=True, nullable=False)  # Ej: SFE, CVR4
    nombre = Column(String, nullable=False)
    email = Column(String)
    telefono = Column(String)
    password_hash = Column(String)
    tarifa_aerea = Column(Numeric)
    tarifa_maritima = Column(Numeric)
    tarifa_china_aerea = Column(Numeric)
    tarifa_china_maritima = Column(Numeric)
    activo = Column(Boolean, default=True)

    paquetes = relationship("Paquete", back_populates="agencia")
    facturas = relationship("Factura", back_populates="agencia")
    pagos = relationship("Pago", back_populates="agencia")


class Paquete(Base):
    """
    Representa un paquete individual dentro de un envío.
    Mapea a la tabla 'paquetes'.

    Nota: un paquete pertenece A UN cliente_cbc O a UNA agencia,
    nunca a ambos. El campo 'tipo_cliente' indica cuál aplica.
    """
    __tablename__ = "paquetes"

    id = Column(Integer, primary_key=True)
    tracking = Column(String, unique=True, index=True)
    nombre_destinatario = Column(String)
    peso = Column(Numeric)
    ruta = Column(String)
    costo = Column(Numeric)
    tarifa_aplicada = Column(Numeric)
    estado_cargo = Column(String)   # en_miami | notificado | entregado
    estado_pago = Column(String)    # pendiente | pagado
    tipo_cliente = Column(String)   # cbc | agencia | mal_identificado
    cliente_cbc_id = Column(Integer, ForeignKey("clientes_cbc.id"), nullable=True)
    agencia_id = Column(Integer, ForeignKey("agencias.id"), nullable=True)
    lote_id = Column(Integer, ForeignKey("lotes.id"), nullable=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=True)
    reasignado = Column(Boolean, default=False)
    fecha_carga = Column(DateTime)

    cliente_cbc = relationship("ClienteCBC", back_populates="paquetes")
    agencia = relationship("Agencia", back_populates="paquetes")
    factura = relationship("Factura", back_populates="paquetes")


class Lote(Base):
    """
    Representa un lote de paquetes agrupados para un mismo envío/ruta.
    Mapea a la tabla 'lotes'.
    """
    __tablename__ = "lotes"

    id = Column(Integer, primary_key=True)
    codigo = Column(String, unique=True)  # Ej: LOT-20260805-0001
    ruta = Column(String)
    estado = Column(String)  # abierto | aprobado
    aprobado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_aprobacion = Column(DateTime)


class Factura(Base):
    """
    Representa una factura emitida a un cliente_cbc o a una agencia.
    Mapea a la tabla 'facturas'.
    """
    __tablename__ = "facturas"

    id = Column(Integer, primary_key=True)
    codigo = Column(String, unique=True)  # Ej: FAC-00001
    numero = Column(String)
    lote_id = Column(Integer, ForeignKey("lotes.id"), nullable=True)
    tipo_cliente = Column(String)  # cbc | agencia
    cliente_cbc_id = Column(Integer, ForeignKey("clientes_cbc.id"), nullable=True)
    agencia_id = Column(Integer, ForeignKey("agencias.id"), nullable=True)
    subtotal = Column(Numeric)
    total = Column(Numeric)
    estado = Column(String)  # pendiente | parcial | pagado
    fecha_emision = Column(DateTime)
    descripcion = Column(Text)

    cliente_cbc = relationship("ClienteCBC", back_populates="facturas")
    agencia = relationship("Agencia", back_populates="facturas")
    paquetes = relationship("Paquete", back_populates="factura")
    pagos = relationship("Pago", back_populates="factura")


class Pago(Base):
    """
    Representa un pago aplicado a una factura.
    Mapea a la tabla 'pagos'.
    """
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=True)
    tipo_cliente = Column(String)  # cbc | agencia
    cliente_cbc_id = Column(Integer, ForeignKey("clientes_cbc.id"), nullable=True)
    agencia_id = Column(Integer, ForeignKey("agencias.id"), nullable=True)
    monto = Column(Numeric)
    metodo = Column(String)  # yappy | ach | efectivo | otro
    referencia = Column(String)
    fecha_pago = Column(DateTime)
    anulado = Column(Boolean, default=False)
    registrado_por = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    factura = relationship("Factura", back_populates="pagos")
    cliente_cbc = relationship("ClienteCBC", back_populates="pagos")
    agencia = relationship("Agencia", back_populates="pagos")
    