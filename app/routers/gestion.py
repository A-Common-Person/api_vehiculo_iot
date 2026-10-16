from fastapi import APIRouter, Depends, Path

from app.schemas.gestion import (
    ComandoActualizarIn,
    ComandoIn,
    DemoActualizarIn,
    DemoIn,
    MovimientoDemoIn,
    RespuestaEscritura,
    VehiculoActualizarIn,
    VehiculoIn,
)
from app.security import verificar_api_key
from app.services.gestion_service import GestionService

router = APIRouter(prefix="/vehiculos")
servicio = GestionService()

AUTH = [Depends(verificar_api_key)]
R_ESCRITURA = {
    404: {"description": "El recurso no existe o no pertenece al vehículo"},
    409: {"description": "Recurso inactivo o conflicto con datos relacionados"},
    422: {"description": "Datos de entrada inválidos"},
    503: {"description": "Base de datos no disponible"},
}
R_ELIMINAR = {
    **R_ESCRITURA,
    401: {"description": "Falta la API key"},
    403: {"description": "API key inválida"},
}

ID_VEHICULO = Path(gt=0, description="ID del vehículo")
ID_COMANDO = Path(gt=0, description="ID del comando")
ID_DEMO = Path(gt=0, description="ID de la DEMO")
ID_MOVIMIENTO = Path(gt=0, description="ID del movimiento de la DEMO")


# ---------------- Vehículos ----------------
@router.post(
    "",
    response_model=RespuestaEscritura,
    status_code=201,
    tags=["Vehículos"],
    summary="Crear un vehículo",
    description="**SP:** sp_crear_vehiculo.",
    responses=R_ESCRITURA,
)
def crear_vehiculo(datos: VehiculoIn):
    return servicio.crear_vehiculo(datos)


@router.post(
    "/{id_vehiculo}/actualizar",
    response_model=RespuestaEscritura,
    tags=["Vehículos"],
    summary="Actualizar un vehículo",
    description="**SP:** sp_obtener_vehiculo, sp_actualizar_vehiculo.",
    responses=R_ESCRITURA,
)
def actualizar_vehiculo(datos: VehiculoActualizarIn, id_vehiculo: int = ID_VEHICULO):
    return servicio.actualizar_vehiculo(id_vehiculo, datos)


@router.post(
    "/{id_vehiculo}/eliminar",
    response_model=RespuestaEscritura,
    tags=["Vehículos"],
    summary="Eliminar un vehículo",
    description="Requiere API key. **SP:** sp_obtener_vehiculo, sp_eliminar_vehiculo.",
    responses=R_ELIMINAR,
    dependencies=AUTH,
)
def eliminar_vehiculo(id_vehiculo: int = ID_VEHICULO):
    return servicio.eliminar_vehiculo(id_vehiculo)


# ---------------- Comandos ----------------
@router.post(
    "/{id_vehiculo}/comandos",
    response_model=RespuestaEscritura,
    status_code=201,
    tags=["Comandos"],
    summary="Crear un comando en el catálogo del vehículo",
    description=(
        "Agrega un comando nuevo al catálogo; no ejecuta ningún movimiento. "
        "**SP:** sp_obtener_vehiculo, sp_crear_comando."
    ),
    responses=R_ESCRITURA,
)
def crear_comando(datos: ComandoIn, id_vehiculo: int = ID_VEHICULO):
    return servicio.crear_comando(id_vehiculo, datos)


@router.post(
    "/{id_vehiculo}/comandos/{id_comando}/actualizar",
    response_model=RespuestaEscritura,
    tags=["Comandos"],
    summary="Actualizar un comando",
    description=(
        "**SP:** sp_obtener_vehiculo, sp_obtener_comandos_vehiculo, "
        "sp_actualizar_comando."
    ),
    responses=R_ESCRITURA,
)
def actualizar_comando(
    datos: ComandoActualizarIn,
    id_vehiculo: int = ID_VEHICULO,
    id_comando: int = ID_COMANDO,
):
    return servicio.actualizar_comando(id_vehiculo, id_comando, datos)


@router.post(
    "/{id_vehiculo}/comandos/{id_comando}/eliminar",
    response_model=RespuestaEscritura,
    tags=["Comandos"],
    summary="Eliminar un comando",
    description=(
        "Requiere API key. **SP:** sp_obtener_vehiculo, "
        "sp_obtener_comandos_vehiculo, sp_eliminar_comando."
    ),
    responses=R_ELIMINAR,
    dependencies=AUTH,
)
def eliminar_comando(id_vehiculo: int = ID_VEHICULO, id_comando: int = ID_COMANDO):
    return servicio.eliminar_comando(id_vehiculo, id_comando)


# ---------------- DEMO ----------------
@router.post(
    "/{id_vehiculo}/demos",
    response_model=RespuestaEscritura,
    status_code=201,
    tags=["DEMO"],
    summary="Crear una DEMO",
    description="**SP:** sp_obtener_vehiculo, sp_crear_demo.",
    responses=R_ESCRITURA,
)
def crear_demo(datos: DemoIn, id_vehiculo: int = ID_VEHICULO):
    return servicio.crear_demo(id_vehiculo, datos)


@router.post(
    "/{id_vehiculo}/demos/{id_demo}/actualizar",
    response_model=RespuestaEscritura,
    tags=["DEMO"],
    summary="Actualizar una DEMO",
    description="**SP:** sp_obtener_demos, sp_actualizar_demo.",
    responses=R_ESCRITURA,
)
def actualizar_demo(
    datos: DemoActualizarIn,
    id_vehiculo: int = ID_VEHICULO,
    id_demo: int = ID_DEMO,
):
    return servicio.actualizar_demo(id_vehiculo, id_demo, datos)


@router.post(
    "/{id_vehiculo}/demos/{id_demo}/eliminar",
    response_model=RespuestaEscritura,
    tags=["DEMO"],
    summary="Eliminar una DEMO",
    description="Requiere API key. **SP:** sp_obtener_demos, sp_eliminar_demo.",
    responses=R_ELIMINAR,
    dependencies=AUTH,
)
def eliminar_demo(id_vehiculo: int = ID_VEHICULO, id_demo: int = ID_DEMO):
    return servicio.eliminar_demo(id_vehiculo, id_demo)


# ---------------- Movimientos de DEMO ----------------
@router.post(
    "/{id_vehiculo}/demos/{id_demo}/movimientos",
    response_model=RespuestaEscritura,
    status_code=201,
    tags=["DEMO"],
    summary="Agregar un movimiento a una DEMO",
    description=(
        "El comando debe pertenecer al vehículo y estar activo. "
        "**SP:** sp_obtener_demos, sp_obtener_comandos_vehiculo, "
        "sp_agregar_movimiento_demo."
    ),
    responses=R_ESCRITURA,
)
def agregar_movimiento(
    datos: MovimientoDemoIn,
    id_vehiculo: int = ID_VEHICULO,
    id_demo: int = ID_DEMO,
):
    return servicio.agregar_movimiento(id_vehiculo, id_demo, datos)


@router.post(
    "/{id_vehiculo}/demos/{id_demo}/movimientos/{id_movimiento}/actualizar",
    response_model=RespuestaEscritura,
    tags=["DEMO"],
    summary="Actualizar un movimiento de una DEMO",
    description=(
        "**SP:** sp_obtener_movimientos_demo, sp_obtener_comandos_vehiculo, "
        "sp_actualizar_movimiento_demo."
    ),
    responses=R_ESCRITURA,
)
def actualizar_movimiento(
    datos: MovimientoDemoIn,
    id_vehiculo: int = ID_VEHICULO,
    id_demo: int = ID_DEMO,
    id_movimiento: int = ID_MOVIMIENTO,
):
    return servicio.actualizar_movimiento(id_vehiculo, id_demo, id_movimiento, datos)


@router.post(
    "/{id_vehiculo}/demos/{id_demo}/movimientos/{id_movimiento}/eliminar",
    response_model=RespuestaEscritura,
    tags=["DEMO"],
    summary="Eliminar un movimiento de una DEMO",
    description=(
        "Requiere API key. **SP:** sp_obtener_movimientos_demo, "
        "sp_eliminar_movimiento_demo."
    ),
    responses=R_ELIMINAR,
    dependencies=AUTH,
)
def eliminar_movimiento(
    id_vehiculo: int = ID_VEHICULO,
    id_demo: int = ID_DEMO,
    id_movimiento: int = ID_MOVIMIENTO,
):
    return servicio.eliminar_movimiento(id_vehiculo, id_demo, id_movimiento)