from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, StringConstraints

from app.schemas.autenticacion import Correo, MAX_LONGITUD_PASSWORD, MIN_LONGITUD_PASSWORD, UsuarioOut
from app.schemas.consultas import VehiculoOut


IdPositivo = Annotated[int, Field(strict=True, gt=0, le=2**64 - 1)]
IdModelo = Annotated[int, Field(strict=True, gt=0, le=2**31 - 1)]
NombreInventario = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
DescripcionInventario = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
EstadoEditable = Literal["disponible", "exhibicion", "inactivo"]


class AltaCliente(BaseModel):
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    correo: Correo
    password: SecretStr = Field(min_length=MIN_LONGITUD_PASSWORD, max_length=MAX_LONGITUD_PASSWORD)

    model_config = ConfigDict(json_schema_extra={
        "examples": [{"nombre": "Comprador de prueba", "correo": "cliente@ejemplo.test", "password": "elige-tu-contraseña"}],
    })


class ClienteOut(UsuarioOut):
    activo: bool


class AltaModelo(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "examples": [{"nombre": "Excavadora de exhibición", "descripcion": "Modelo para demostraciones"}],
    })

    nombre: NombreInventario
    descripcion: DescripcionInventario | None = None


class EditarModelo(AltaModelo):
    model_config = ConfigDict(json_schema_extra={
        "examples": [{"nombre": "Excavadora de exhibición", "descripcion": "Modelo para demostraciones", "activo": True}],
    })

    activo: StrictBool


class ModeloOut(BaseModel):
    id_modelo: int
    nombre: str
    descripcion: str | None
    activo: bool


class ModeloCatalogoOut(ModeloOut):
    codigos: list[int]
    codigos_invitado: list[int]


class CapacidadOut(BaseModel):
    codigo: int
    nombre: str


class GuardarCapacidades(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigos: set[Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)]] = Field(
        description="Comandos habilitados del modelo. DETENER se controla por la configuración de cada unidad."
    )


class DatosUnidad(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: NombreInventario
    descripcion: DescripcionInventario | None = None
    microcontrolador: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = None


class CargaMovimientos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_modelo: IdModelo
    codigos: set[Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)]] = Field(min_length=1)


class MovimientoUnidadOut(CapacidadOut):
    activo: bool


class CambiosMovimientos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_modelo: IdModelo
    habilitar: set[IdModelo]
    deshabilitar: set[IdModelo]


class AltaUnidad(DatosUnidad):
    model_config = ConfigDict(json_schema_extra={
        "examples": [{"nombre": "Excavadora de prueba", "id_modelo": 1, "microcontrolador": "ESP8266"}],
    })

    id_modelo: IdModelo
    estado_comercial: EstadoEditable = "disponible"


class EditarUnidad(DatosUnidad):
    id_modelo: IdModelo | None
    estado_comercial: EstadoEditable | None = Field(
        default=None, description="Omite el estado para conservarlo. Inactivo conserva el identificador y el historial."
    )


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
    actor_nombre: str | None
    actor_rol: str | None
    unidad_nombre: str | None
    id_evento: int
    id_reserva: int | None
    id_usuario: int | None
    id_vehiculo: int | None
    accion: str
    detalle: dict | None
    ocurrio_en: datetime
