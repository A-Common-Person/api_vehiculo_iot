from pydantic import BaseModel, Field


class MovimientoRequest(BaseModel):
    id_comando: int = Field(gt=0, description="ID del comando del catálogo del vehículo")


class MovimientoResponse(BaseModel):
    id_vehiculo: int
    id_comando: int
    comando: str
    codigo: int
    origen: str
    conectado: bool