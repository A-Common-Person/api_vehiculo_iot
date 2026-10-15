from fastapi import APIRouter, Path

from app.schemas.movimiento import MovimientoRequest, MovimientoResponse
from app.services.movimiento_service import MovimientoService

router = APIRouter(prefix="/vehiculos", tags=["Estado"])
servicio = MovimientoService()


@router.post(
    "/{id_vehiculo}/movimientos",
    response_model=MovimientoResponse,
    status_code=201,
    summary="Registrar un movimiento individual",
    description=(
        "Valida el vehículo y el comando, actualiza el estado y registra el "
        "movimiento en el historial dentro de una misma transacción. "
        "**SP:** sp_obtener_vehiculo, sp_obtener_comandos_vehiculo, "
        "sp_obtener_estado, sp_actualizar_estado, sp_registrar_historial."
    ),
    responses={
        404: {"description": "El vehículo o el comando no existe"},
        409: {"description": "El vehículo o el comando está inactivo"},
        422: {"description": "Datos de entrada inválidos"},
        503: {"description": "Base de datos no disponible"},
    },
)
def registrar_movimiento(
    datos: MovimientoRequest,
    id_vehiculo: int = Path(gt=0, description="ID del vehículo"),
):
    return servicio.ejecutar(id_vehiculo, datos.id_comando)