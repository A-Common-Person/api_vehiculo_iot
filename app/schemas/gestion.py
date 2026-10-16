from pydantic import BaseModel, Field


class VehiculoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    modelo: str | None = Field(default=None, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)
    microcontrolador: str | None = Field(default=None, max_length=100)


class VehiculoActualizarIn(VehiculoIn):
    activo: bool


class ComandoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    codigo: int = Field(ge=0)
    descripcion: str | None = Field(default=None, max_length=255)


class ComandoActualizarIn(ComandoIn):
    activo: bool


class DemoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)


class DemoActualizarIn(DemoIn):
    activo: bool


class MovimientoDemoIn(BaseModel):
    id_comando: int = Field(gt=0)
    orden: int = Field(gt=0)
    duracion_ms: int = Field(ge=0, le=600000)
    pausa_ms: int = Field(ge=0, le=600000)


class RespuestaEscritura(BaseModel):
    mensaje: str
    resultado: list[dict] = []