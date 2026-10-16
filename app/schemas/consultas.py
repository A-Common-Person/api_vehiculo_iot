from datetime import datetime

from pydantic import BaseModel


class VehiculoOut(BaseModel):
    id_vehiculo: int
    nombre: str
    modelo: str | None = None
    descripcion: str | None = None
    microcontrolador: str | None = None
    fecha_registro: datetime
    activo: bool


class ComandoOut(BaseModel):
    id_comando: int
    id_vehiculo: int
    nombre: str
    codigo: int
    descripcion: str | None = None
    activo: bool


class EstadoOut(BaseModel):
    id_vehiculo: int
    vehiculo: str
    id_comando: int
    comando: str
    codigo: int
    conectado: bool
    fecha_actualizacion: datetime


class HistorialOut(BaseModel):
    id_historial: int
    id_vehiculo: int
    comando: str
    codigo: int
    fecha_hora: datetime
    origen: str


class DemoOut(BaseModel):
    id_demo: int
    id_vehiculo: int
    nombre: str
    descripcion: str | None = None
    activo: bool


class MovimientoDemoOut(BaseModel):
    id_demo_movimiento: int
    orden: int
    id_comando: int
    comando: str
    codigo: int
    duracion_ms: int
    pausa_ms: int


class VehiculoDetalleOut(VehiculoOut):
    comandos: list[ComandoOut]
    estado: EstadoOut | None = None
    demos: list[DemoOut]