from pydantic import BaseModel


class DemoIniciadaResponse(BaseModel):
    id_vehiculo: int
    id_demo: int
    total_movimientos: int
    mensaje: str


class DemoCanceladaResponse(BaseModel):
    id_vehiculo: int
    mensaje: str