from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel

from app.dependencias_autenticacion import sesion_actual
from app.repositories.control_repository import ControlNoAutorizado
from app.schemas.autenticacion import SesionActual
from app.services.control_service import DURACION_MAXIMA_MS, control


router = APIRouter(prefix="/vehiculos", tags=["Control de prueba"])
Unidad = Annotated[int, Path(gt=0, le=2**31 - 1)]
Sesion = Annotated[SesionActual, Depends(sesion_actual)]


class OrdenPrueba(BaseModel):
    accion: Literal["avanzar", "detener"]


class ResultadoOrden(BaseModel):
    avance_confirmado: bool
    detencion_confirmada: bool


@router.get("/{unidad}/control/prueba")
async def estado_de_prueba(unidad: Unidad, sesion: Sesion):
    try:
        conectado = await control.estado(unidad, sesion.id_sesion)
    except ControlNoAutorizado:
        raise HTTPException(403, "No tienes permiso para operar este vehículo") from None
    return {"dispositivo_en_linea": conectado, "maximo_avance_ms": DURACION_MAXIMA_MS}


@router.post(
    "/{unidad}/control/prueba", response_model=ResultadoOrden,
    responses={
        401: {"description": "Sesión inválida"},
        403: {"description": "Permiso por asignación insuficiente"},
        409: {"description": "Vehículo desconectado u ocupado"},
        504: {"description": "La orden no se pudo confirmar en el dispositivo"},
    },
)
async def enviar_orden(unidad: Unidad, datos: OrdenPrueba, sesion: Sesion):
    avanzar = datos.accion == "avanzar"
    try:
        resultado = await control.ejecutar(unidad, sesion.id_sesion, avanzar=avanzar)
    except ControlNoAutorizado:
        raise HTTPException(403, "No tienes permiso para operar este vehículo") from None
    if not resultado["detencion_confirmada"]:
        raise HTTPException(504, "El dispositivo no confirmó DETENER")
    if avanzar and not resultado["avance_confirmado"]:
        raise HTTPException(504, "El avance no fue confirmado y DETENER sí se confirmó")
    return resultado
