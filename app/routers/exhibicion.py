import asyncio
from collections import OrderedDict
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from app.config import ORIGENES_CLIENTE
from app.dependencias_autenticacion import bearer, no_autenticado
from app.exceptions import ReglaNegocioError
from app.repositories.comando_repository import CODIGO_DETENER
from app.schemas.exhibicion import CredencialExhibicion, MensajeExhibicion, ModeloExhibicionOut, ReservaExhibicionOut
from app.services.exhibicion_service import exhibir


router = APIRouter(tags=["Exhibición"])
Unidad = Annotated[int, Path(gt=0, le=2**31 - 1)]
intentos = OrderedDict()
VENTANA_S = 60
MAX_INTENTOS = 6


@router.get("/exhibicion/catalogo", response_model=list[ModeloExhibicionOut])
async def catalogo():
    return await exhibir.catalogo()


@router.post("/exhibicion/unidades/{unidad}/sesiones", response_model=ReservaExhibicionOut, status_code=201)
async def solicitar_sesion(unidad: Unidad, request: Request):
    ip = request.client.host if request.client is not None else "local"
    ahora = monotonic()
    while intentos and next(iter(intentos.values()))[0] <= ahora:
        intentos.popitem(last=False)
    anterior = intentos.get(ip)
    if anterior is None:
        if len(intentos) >= 4096:
            raise HTTPException(429, "Hay muchas solicitudes. Intenta en un minuto")
        intentos[ip] = (ahora + VENTANA_S, 1)
    elif anterior[1] < MAX_INTENTOS:
        intentos[ip] = (anterior[0], anterior[1] + 1)
    else:
        raise HTTPException(429, "Espera un minuto antes de solicitar otra prueba")
    return await exhibir.reservar(unidad)


@router.delete("/exhibicion/sesion")
async def terminar_sesion(credencial: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    reserva = exhibir.identificar(credencial.credentials) if credencial else None
    if reserva is None:
        raise no_autenticado("Se requiere una sesión de invitado vigente")
    reserva.terminar("solicitada")
    await reserva.finalizada.wait()
    return {"detencion_confirmada": reserva.confirmo_detener, "reserva_cerrada": reserva.cerro_reserva}


async def _texto(websocket):
    texto = await websocket.receive_text()
    if len(texto) > 512:
        raise ValueError("Trama demasiado larga")
    return texto


@router.websocket("/ws/exhibicion")
async def canal_exhibicion(websocket: WebSocket):
    if websocket.headers.get("origin") not in ORIGENES_CLIENTE:
        await websocket.close(1008, "Origen no permitido")
        return
    await websocket.accept()
    reserva = None
    espera_fin = None
    recibir = None
    envio = asyncio.Lock()

    async def publicar(tipo, **datos):
        async with envio:
            await asyncio.wait_for(websocket.send_json({"tipo": tipo, **datos}), timeout=1)

    try:
        trama = await asyncio.wait_for(_texto(websocket), timeout=4)
        credencial = CredencialExhibicion.model_validate_json(trama).token.get_secret_value()
        activa = exhibir.identificar(credencial)
        if activa is None or activa.cerrar.is_set() or not activa.segundos():
            await websocket.close(4401, "Sesión de invitado vencida o inválida")
            return
        if activa.canal:
            await websocket.close(4409, "Esta sesión ya tiene un canal de control")
            return
        reserva = activa
        reserva.canal = True
        reserva.ultimo_contacto = monotonic()
        espera_fin = asyncio.create_task(reserva.finalizada.wait())
        await publicar("lista", segundos=reserva.segundos())
        while not reserva.cerrar.is_set():
            recibir = asyncio.create_task(_texto(websocket))
            listas, _ = await asyncio.wait((recibir, espera_fin), return_when=asyncio.FIRST_COMPLETED)
            if espera_fin in listas:
                break
            datos = MensajeExhibicion.model_validate_json(await recibir)
            reserva.ultimo_contacto = monotonic()
            if datos.tipo == "finalizar":
                reserva.terminar("solicitada")
            elif datos.tipo == "latido":
                await publicar("vigente", segundos=reserva.segundos())
            elif datos.codigo == CODIGO_DETENER:
                if await exhibir.detener(reserva):
                    await publicar("detenido", codigo=CODIGO_DETENER)
            else:
                try:
                    exhibir.mover(reserva, datos.codigo, publicar)
                except ReglaNegocioError as error:
                    await publicar("rechazada", mensaje=str(error))
        await reserva.finalizada.wait()
        await publicar("finalizada", motivo=reserva.motivo, detencion_confirmada=reserva.confirmo_detener,
                       reserva_cerrada=reserva.cerro_reserva)
        await websocket.close()
    except (ValidationError, ValueError, TimeoutError):
        await websocket.close(1008, "Mensaje de exhibición inválido")
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        tareas = tuple(t for t in (recibir, espera_fin) if t is not None)
        for tarea in tareas:
            if not tarea.done():
                tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)
        if reserva is not None:
            reserva.terminar("canal_desconectado")
            await reserva.finalizada.wait()
