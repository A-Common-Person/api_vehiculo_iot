import asyncio
import json
from typing import Annotated

import pymysql
from fastapi import APIRouter, Path, WebSocket, WebSocketDisconnect, WebSocketException

from app.config import ORIGENES_CLIENTE
from app.dependencias_autenticacion import autenticacion
from app.repositories.estado_repository import EstadoRepository
from app.repositories.inventario_repository import inventario
from app.services.control_service import control
from app.websocket.manager import Suscripcion, evento_estado_actual, manager


router = APIRouter()
estados = EstadoRepository()
PLAZO_AUTENTICACION = 5
INTERVALO_REVALIDACION = 5
LIMITE_AUTENTICACION = 512


async def _consultar(funcion, *parametros):
    try:
        return await asyncio.to_thread(funcion, *parametros)
    except pymysql.MySQLError:
        raise WebSocketException(code=1011, reason="Base de datos no disponible") from None


async def _autenticar(websocket):
    try:
        trama = await asyncio.wait_for(websocket.receive(), timeout=PLAZO_AUTENTICACION)
    except TimeoutError:
        raise WebSocketException(code=4401, reason="No se recibió la autenticación a tiempo") from None
    if trama["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(trama["code"])

    texto = trama.get("text")
    if not isinstance(texto, str):
        raise WebSocketException(code=4401, reason="Se requiere autenticación JSON")
    if len(texto) > LIMITE_AUTENTICACION:
        raise WebSocketException(code=1009, reason="Mensaje demasiado grande")
    try:
        datos = json.loads(texto)
    except (ValueError, RecursionError):
        raise WebSocketException(code=4401, reason="Se requiere autenticación JSON") from None
    if not isinstance(datos, dict) or datos.keys() != {"tipo", "token"} or datos["tipo"] != "autenticar":
        raise WebSocketException(code=4401, reason="Se requiere el mensaje autenticar")
    if not isinstance(datos["token"], str):
        raise WebSocketException(code=4401, reason="Se requiere un token de sesión")

    sesion = await _consultar(autenticacion.identificar, datos["token"])
    if sesion is None:
        raise WebSocketException(code=4401, reason="Sesión inválida o vencida")
    return sesion


def _autorizar_lectura(id_vehiculo, sesion):
    if sesion is None:
        raise WebSocketException(code=4401, reason="Sesión inválida o vencida")
    if not inventario.puede_consultar(id_vehiculo, sesion.usuario):
        raise WebSocketException(code=4403, reason="No tienes acceso a este vehículo")


def _verificar_canal(id_vehiculo, id_sesion, mensaje):
    sesion = autenticacion.revalidar(id_sesion)
    _autorizar_lectura(id_vehiculo, sesion)
    id_demo = mensaje.get("id_demo") if mensaje else None
    if id_demo is None:
        return True
    return id_demo not in inventario.demos_privadas_ajenas(id_vehiculo, sesion.usuario.id_usuario)


class TelemetriaPublica(Suscripcion):
    async def enviar_o_revalidar(self, mensaje=None):
        if mensaje is not None:
            if mensaje.get("evento") not in {"estado_actual", "movimiento"} or mensaje.get("id_demo") is not None:
                mensaje = None
            else:
                campos = ("evento", "id_vehiculo", "comando", "codigo", "timestamp", "conectado")
                mensaje = {campo: mensaje[campo] for campo in campos if campo in mensaje}
        return await super().enviar_o_revalidar(mensaje)


@router.websocket("/ws/vehiculos/{id_vehiculo}")
async def monitorear_vehiculo(
    websocket: WebSocket,
    id_vehiculo: Annotated[int, Path(gt=0, le=2**31 - 1)],
):
    cliente_web = websocket.headers.get("origin") in ORIGENES_CLIENTE
    if not cliente_web and id_vehiculo != 1:
        await websocket.close(code=1008, reason="Origen no permitido")
        return
    await websocket.accept()

    canal = None
    try:
        if cliente_web:
            sesion = await _autenticar(websocket)
            await _consultar(_autorizar_lectura, id_vehiculo, sesion)

            async def autorizar(mensaje):
                return await _consultar(_verificar_canal, id_vehiculo, sesion.id_sesion, mensaje)

            canal = Suscripcion(websocket, id_sesion=sesion.id_sesion, autorizar=autorizar)
        else:
            canal = TelemetriaPublica(websocket)
        estado = await _consultar(estados.obtener, id_vehiculo)
        manager.agregar(id_vehiculo, canal)
        if not await canal.enviar_o_revalidar(evento_estado_actual(id_vehiculo, estado)):
            return

        while True:
            try:
                trama = await asyncio.wait_for(websocket.receive(), timeout=INTERVALO_REVALIDACION)
            except TimeoutError:
                if not await canal.enviar_o_revalidar():
                    return
            else:
                if trama["type"] != "websocket.disconnect":
                    await canal.cerrar(1008, "El canal sólo transmite eventos del vehículo")
                return
    except WebSocketException as error:
        if canal is None:
            await websocket.close(code=error.code, reason=error.reason)
        else:
            await canal.cerrar(error.code, error.reason)
    except (WebSocketDisconnect, OSError):
        pass
    finally:
        if canal is not None:
            manager.quitar(id_vehiculo, websocket)
            if canal.id_sesion is not None:
                control.detener_demo_de_sesion(id_vehiculo, canal.id_sesion)
