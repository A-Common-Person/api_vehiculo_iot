from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, StrictInt, UUID4

from app.dependencias_autenticacion import sesion_actual
from app.repositories.comando_repository import CODIGO_AVANZAR, CODIGO_DETENER, CODIGOS_CONTROL
from app.repositories.control_repository import ControlNoAutorizado
from app.schemas.autenticacion import SesionActual
from app.schemas.demo import DemoAceptadaResponse, DemoCanceladaResponse
from app.services.control_service import control


router = APIRouter(prefix="/vehiculos", tags=["Control de prueba"])
Unidad = Annotated[int, Path(gt=0, le=2**31 - 1)]
Sesion = Annotated[SesionActual, Depends(sesion_actual)]
AccionPrueba = Literal["avanzar", "detener"]


class OrdenPrueba(BaseModel):
    accion: AccionPrueba


class EstadoControlPrueba(BaseModel):
    dispositivo_en_linea: bool
    maximo_avance_ms: int
    acciones_habilitadas: list[AccionPrueba]
    codigos_habilitados: list[int]
    id_enlace: UUID4 | None
    mantenido: bool
    demo_disponible: bool
    id_demo_activa: int | None
    id_ejecucion_demo: UUID4 | None


class ResultadoOrden(BaseModel):
    avance_confirmado: bool
    detencion_confirmada: bool


class OrdenManual(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: StrictInt
    id_enlace: UUID4
    id_movimiento: UUID4 | None = None


class InicioDemo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_enlace: UUID4


class ResultadoManual(BaseModel):
    orden_confirmada: bool
    detencion_confirmada: bool


@router.get("/{unidad}/control/prueba", response_model=EstadoControlPrueba)
async def estado_de_prueba(unidad: Unidad, sesion: Sesion):
    try:
        return await control.estado(unidad, sesion.id_sesion)
    except ControlNoAutorizado:
        raise HTTPException(403, "No tienes permiso para operar este vehículo") from None


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
    resultado = await _ejecutar(unidad, sesion, CODIGO_AVANZAR if avanzar else CODIGO_DETENER)
    return {"avance_confirmado": avanzar and resultado["orden_confirmada"], "detencion_confirmada": True}


@router.post(
    "/{unidad}/control/orden", response_model=ResultadoManual,
    responses={
        403: {"description": "Falta la asignación vigente"},
        409: {"description": "Comando bloqueado, unidad desconectada u ocupada"},
        504: {"description": "La orden no se confirmó en el dispositivo"},
    },
)
async def enviar_orden_manual(unidad: Unidad, datos: OrdenManual, sesion: Sesion):
    if datos.codigo not in CODIGOS_CONTROL:
        raise HTTPException(422, "El código no pertenece a los mandos de Control")
    if datos.codigo != CODIGO_DETENER and datos.id_movimiento is None:
        raise HTTPException(422, "Indica el identificador del movimiento")
    return await _ejecutar(unidad, sesion, datos.codigo, datos.id_enlace, datos.id_movimiento)


@router.post("/{unidad}/demos/{id_demo}/iniciar", response_model=DemoAceptadaResponse, status_code=202,
             tags=["DEMO"], summary="Ejecutar una demo autorizada en la unidad")
async def iniciar_demo(unidad: Unidad, id_demo: Annotated[int, Path(gt=0, le=2**31 - 1)],
                       datos: InicioDemo, sesion: Sesion):
    try:
        return await control.iniciar_demo(unidad, sesion.id_sesion, id_demo, datos.id_enlace)
    except ControlNoAutorizado:
        raise HTTPException(403, "No tienes permiso para operar este vehículo") from None


@router.post("/{unidad}/demos/cancelar", response_model=DemoCanceladaResponse,
             tags=["DEMO"], summary="Cancelar una demo con DETENER confirmado")
async def cancelar_demo(unidad: Unidad, sesion: Sesion):
    try:
        detencion = await control.cancelar_demo(unidad, sesion.id_sesion)
    except ControlNoAutorizado:
        raise HTTPException(403, "No tienes permiso para operar este vehículo") from None
    if not detencion:
        raise HTTPException(504, "El ESP8266 no confirmó DETENER")
    return {"id_vehiculo": unidad, "mensaje": "DETENER confirmado por el ESP8266"}


async def _ejecutar(unidad, sesion, codigo, id_enlace=None, id_movimiento=None):
    try:
        resultado = await control.ejecutar(
            unidad, sesion.id_sesion, codigo=codigo, id_enlace=id_enlace, id_movimiento=id_movimiento
        )
    except ControlNoAutorizado:
        raise HTTPException(403, "No tienes permiso para operar este vehículo") from None
    if not resultado["detencion_confirmada"]:
        raise HTTPException(504, "El dispositivo no confirmó DETENER")
    if not resultado["orden_confirmada"]:
        raise HTTPException(504, "Se confirmó DETENER. La orden anterior quedó sin confirmación")
    return resultado
