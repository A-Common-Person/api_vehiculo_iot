from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints

from app.schemas.autenticacion import Correo, MAX_LONGITUD_PASSWORD, MIN_LONGITUD_PASSWORD, UsuarioOut
from app.schemas.consultas import VehiculoOut


IdPositivo = Annotated[int, Field(strict=True, gt=0, le=2**64 - 1)]


class AltaCliente(BaseModel):
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    correo: Correo
    password: SecretStr = Field(min_length=MIN_LONGITUD_PASSWORD, max_length=MAX_LONGITUD_PASSWORD)

    model_config = ConfigDict(json_schema_extra={
        "examples": [{"nombre": "Comprador de prueba", "correo": "cliente@ejemplo.test", "password": "elige-tu-contraseña"}],
    })


class ClienteOut(UsuarioOut):
    activo: bool


class UnidadInventarioOut(VehiculoOut):
    id_modelo: int | None
    modelo_comercial: str | None
    estado_comercial: Literal["disponible", "asignado", "exhibicion", "inactivo"]
    id_asignacion: int | None
    id_propietario: int | None


class AsignarUnidad(BaseModel):
    id_usuario: IdPositivo
    id_asignacion_esperada: IdPositivo | None = Field(
        default=None, description="Indica la asignación vigente al reasignar una unidad."
    )

    model_config = ConfigDict(json_schema_extra={"examples": [{"id_usuario": 2}]})


class AsignacionOut(BaseModel):
    id_asignacion: int
    id_vehiculo: int
    id_usuario: int
    inicia_en: datetime
    finaliza_en: datetime | None


class EventoAuditoriaOut(BaseModel):
    id_evento: int
    id_usuario: int | None
    id_vehiculo: int | None
    accion: str
    detalle: dict | None
    ocurrio_en: datetime
