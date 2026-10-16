from fastapi import APIRouter, Depends, Path

from app.schemas.demo import DemoCanceladaResponse, DemoIniciadaResponse
from app.security import verificar_api_key
from app.services.demo_service import DemoService

router = APIRouter(prefix="/vehiculos", tags=["DEMO"])
servicio = DemoService()


@router.post(
    "/{id_vehiculo}/demos/{id_demo}/iniciar",
    response_model=DemoIniciadaResponse,
    status_code=202,
    summary="Iniciar una DEMO",
    description=(
        "Inicia en segundo plano una DEMO existente y activa del vehículo. Los "
        "movimientos se transmiten por WebSocket con sus tiempos y **no** se "
        "registran en el historial. Requiere API key. "
        "**SP:** sp_obtener_vehiculo, sp_obtener_demos, "
        "sp_obtener_movimientos_demo, sp_obtener_estado, sp_actualizar_estado."
    ),
    responses={
        401: {"description": "Falta la API key"},
        403: {"description": "API key inválida"},
        404: {"description": "El vehículo o la DEMO no existe"},
        409: {"description": "Ya hay una DEMO en ejecución, o algo está inactivo"},
        503: {"description": "Base de datos no disponible"},
    },
    dependencies=[Depends(verificar_api_key)],
)
async def iniciar_demo(
    id_vehiculo: int = Path(gt=0, description="ID del vehículo"),
    id_demo: int = Path(gt=0, description="ID de la DEMO"),
):
    return await servicio.iniciar(id_vehiculo, id_demo)


@router.post(
    "/{id_vehiculo}/demos/cancelar",
    response_model=DemoCanceladaResponse,
    summary="Cancelar la DEMO en ejecución",
    description=(
        "Detiene de inmediato la emisión de movimientos de la DEMO activa y "
        "emite el evento `demo_cancelada` por WebSocket. Requiere API key."
    ),
    responses={
        401: {"description": "Falta la API key"},
        403: {"description": "API key inválida"},
        404: {"description": "No hay una DEMO en ejecución"},
    },
    dependencies=[Depends(verificar_api_key)],
)
async def cancelar_demo(id_vehiculo: int = Path(gt=0, description="ID del vehículo")):
    return servicio.cancelar(id_vehiculo)