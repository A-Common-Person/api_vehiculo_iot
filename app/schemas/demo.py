from typing import Annotated

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.consultas import DemoOut


class DemoIniciadaResponse(BaseModel):
    id_vehiculo: int
    id_demo: int
    total_movimientos: int
    mensaje: str


class DemoCanceladaResponse(BaseModel):
    id_vehiculo: int
    mensaje: str


DEMO_MIN_PASO_MS = 100
DEMO_MAX_PASO_MS = 3000
DEMO_MAX_PASOS = 20
DEMO_MAX_TOTAL_MS = 30_000


class DemoAceptadaResponse(DemoIniciadaResponse):
    id_ejecucion: UUID


class PasoDemoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_comando: int = Field(strict=True, gt=0, le=2**31 - 1)
    duracion_ms: int = Field(strict=True, ge=DEMO_MIN_PASO_MS, le=DEMO_MAX_PASO_MS)
    pausa_ms: int = Field(default=0, strict=True, ge=0, le=DEMO_MAX_PASO_MS)


class DemoEditableIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    descripcion: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    activo: bool = True
    pasos: list[PasoDemoIn] = Field(min_length=1, max_length=DEMO_MAX_PASOS, description="El orden del listado define la secuencia.")

    @model_validator(mode="after")
    def validar_duracion_total(self):
        if sum(paso.duracion_ms + paso.pausa_ms for paso in self.pasos) > DEMO_MAX_TOTAL_MS:
            raise ValueError("La demo completa admite hasta 30 segundos incluidos los tiempos de pausa")
        return self


class PasoDemoEditableOut(BaseModel):
    id_comando: int
    duracion_ms: int
    pausa_ms: int


class DemoEditableOut(DemoOut):
    pasos: list[PasoDemoEditableOut]


class ComandoEditorOut(BaseModel):
    id_comando: int
    nombre: str
    codigo: int


class EditorDemoOut(BaseModel):
    demos: list[DemoOut]
    comandos: list[ComandoEditorOut]
