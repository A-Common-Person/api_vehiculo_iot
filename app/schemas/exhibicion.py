from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt


CODIGOS_EXHIBICION = {1: "Avanzar", 3: "Girar a la derecha", 4: "Girar a la izquierda", 9: "DETENER"}
DURACION_EXHIBICION_S = 45
MOVIMIENTO_EXHIBICION_MS = 2000


class UnidadExhibicionOut(BaseModel):
    id_vehiculo: int
    disponibilidad: Literal["disponible", "ocupada", "sin_conexion", "sin_configurar"]


class ModeloExhibicionOut(BaseModel):
    id_modelo: int
    nombre: str
    descripcion: str | None
    capacidades: list[str]
    unidades: list[UnidadExhibicionOut]


class MandoExhibicionOut(BaseModel):
    codigo: int
    nombre: str


class ReservaExhibicionOut(BaseModel):
    token: str
    id_vehiculo: int
    segundos: int
    comandos: list[MandoExhibicionOut]


class CredencialExhibicion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["autenticar"]
    token: SecretStr = Field(min_length=43, max_length=43)


class MensajeExhibicion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["latido", "orden", "mantener", "finalizar"]
    codigo: StrictInt | None = None
