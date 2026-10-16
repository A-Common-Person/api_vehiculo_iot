from fastapi import APIRouter, Path

from app.schemas.consultas import (
    ComandoOut,
    DemoOut,
    EstadoOut,
    HistorialOut,
    MovimientoDemoOut,
    VehiculoDetalleOut,
    VehiculoOut,
)
from app.services.consulta_service import ConsultaService

router = APIRouter(prefix="/vehiculos")
servicio = ConsultaService()

NO_ENCONTRADO = {404: {"description": "El recurso no existe"}}
ID_VEHICULO = Path(gt=0, description="ID del vehículo")


@router.get(
    "",
    response_model=list[VehiculoOut],
    tags=["Vehículos"],
    summary="Listar vehículos",
    description="Devuelve todos los vehículos. **SP:** sp_obtener_vehiculos.",
)
def listar_vehiculos():
    return servicio.listar_vehiculos()


@router.get(
    "/{id_vehiculo}",
    response_model=VehiculoDetalleOut,
    tags=["Vehículos"],
    summary="Consultar un vehículo con sus comandos, estado y DEMO",
    description=(
        "**SP:** sp_obtener_vehiculo, sp_obtener_comandos_vehiculo, "
        "sp_obtener_estado, sp_obtener_demos."
    ),
    responses=NO_ENCONTRADO,
)
def detalle_vehiculo(id_vehiculo: int = ID_VEHICULO):
    return servicio.detalle_vehiculo(id_vehiculo)


@router.get(
    "/{id_vehiculo}/comandos",
    response_model=list[ComandoOut],
    tags=["Comandos"],
    summary="Listar el catálogo de comandos de un vehículo",
    description="**SP:** sp_obtener_vehiculo, sp_obtener_comandos_vehiculo.",
    responses=NO_ENCONTRADO,
)
def listar_comandos(id_vehiculo: int = ID_VEHICULO):
    return servicio.comandos(id_vehiculo)


@router.get(
    "/{id_vehiculo}/estado",
    response_model=EstadoOut | None,
    tags=["Estado"],
    summary="Consultar el último estado del vehículo",
    description=(
        "Devuelve `null` si el vehículo existe pero aún no tiene estado. "
        "**SP:** sp_obtener_vehiculo, sp_obtener_estado."
    ),
    responses=NO_ENCONTRADO,
)
def consultar_estado(id_vehiculo: int = ID_VEHICULO):
    return servicio.estado(id_vehiculo)


@router.get(
    "/{id_vehiculo}/historial",
    response_model=list[HistorialOut],
    tags=["Historial"],
    summary="Consultar los últimos 10 movimientos individuales",
    description=(
        "Devuelve como máximo los 10 movimientos individuales más recientes, "
        "del más nuevo al más antiguo. Los movimientos de DEMO nunca aparecen. "
        "**SP:** sp_obtener_vehiculo, sp_obtener_historial."
    ),
    responses=NO_ENCONTRADO,
)
def consultar_historial(id_vehiculo: int = ID_VEHICULO):
    return servicio.historial(id_vehiculo)


@router.get(
    "/{id_vehiculo}/demos",
    response_model=list[DemoOut],
    tags=["DEMO"],
    summary="Listar las DEMO de un vehículo",
    description="**SP:** sp_obtener_vehiculo, sp_obtener_demos.",
    responses=NO_ENCONTRADO,
)
def listar_demos(id_vehiculo: int = ID_VEHICULO):
    return servicio.demos(id_vehiculo)


@router.get(
    "/{id_vehiculo}/demos/{id_demo}/movimientos",
    response_model=list[MovimientoDemoOut],
    tags=["DEMO"],
    summary="Consultar los movimientos ordenados de una DEMO",
    description=(
        "**SP:** sp_obtener_vehiculo, sp_obtener_demos, "
        "sp_obtener_movimientos_demo."
    ),
    responses=NO_ENCONTRADO,
)
def movimientos_demo(
    id_vehiculo: int = ID_VEHICULO,
    id_demo: int = Path(gt=0, description="ID de la DEMO"),
):
    return servicio.movimientos_demo(id_vehiculo, id_demo)