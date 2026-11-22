import asyncio
from hashlib import sha256
from ipaddress import ip_address
import json
import logging
from typing import Annotated

import pymysql
from fastapi import APIRouter, Path, WebSocket, WebSocketDisconnect

from app.repositories.control_repository import ControlRepository
from app.services.autenticacion_service import FORMATO_TOKEN
from app.websocket.dispositivos import EnlaceDispositivo, dispositivos


router = APIRouter()
repositorio = ControlRepository()
logger = logging.getLogger("uvicorn.error.dispositivos")
INTERVALO_REVALIDACION = 10
REINTENTO_REVALIDACION = 3


def _transporte_permitido(websocket):
    if websocket.url.scheme == "wss":
        return True
    return websocket.client is not None and ip_address(websocket.client.host).is_loopback


def _mensaje(trama):
    texto = trama.get("text")
    if not isinstance(texto, str) or len(texto) > 512:
        raise ValueError("Trama inválida")
    try:
        datos = json.loads(texto)
    except RecursionError:
        raise ValueError("Trama inválida") from None
    if not isinstance(datos, dict):
        raise ValueError("Trama inválida")
    return datos


async def _revalidar(enlace):
    espera = INTERVALO_REVALIDACION
    while not enlace.cerrado:
        await asyncio.sleep(espera)
        if enlace.cerrado:
            return
        try:
            vigente = await asyncio.to_thread(repositorio.credencial_vigente, enlace.unidad, enlace.huella)
        except pymysql.MySQLError as error:
            if enlace.credencial_verificada:
                logger.warning(
                    "ESP8266 unidad %s: RDS no respondió a la verificación (%s). Control en pausa",
                    enlace.unidad, error.args[0],
                )
            enlace.credencial_verificada = False
            espera = REINTENTO_REVALIDACION
            continue
        if not vigente:
            await enlace.cerrar(4401, "Credencial del dispositivo revocada o unidad inactiva")
            return
        if not enlace.credencial_verificada:
            logger.info("ESP8266 unidad %s: verificación con RDS recuperada", enlace.unidad)
        enlace.credencial_verificada = True
        espera = INTERVALO_REVALIDACION


@router.websocket("/ws/dispositivos/{unidad}")
async def conectar_dispositivo(websocket: WebSocket, unidad: Annotated[int, Path(gt=0, le=2**31 - 1)]):
    esquema, _, token = websocket.headers.get("authorization", "").partition(" ")
    if not _transporte_permitido(websocket) or esquema.lower() != "bearer" or not FORMATO_TOKEN.fullmatch(token):
        await websocket.close(code=4401)
        return

    huella = sha256(token.encode("ascii")).digest()
    enlace = None
    revalidacion = None
    try:
        if not await asyncio.to_thread(repositorio.credencial_vigente, unidad, huella):
            logger.warning("ESP8266 unidad %s: credencial rechazada", unidad)
            await websocket.close(code=4401)
            return
        await websocket.accept()
        trama = await asyncio.wait_for(websocket.receive(), timeout=8)
        if trama["type"] == "websocket.disconnect":
            logger.info("ESP8266 unidad %s: desconectado antes de listo (%s)", unidad, trama["code"])
            return
        inicio = _mensaje(trama)
        if inicio != {"tipo": "listo", "id_vehiculo": unidad, "salidas_apagadas": True}:
            logger.warning("ESP8266 unidad %s: mensaje de inicio inválido", unidad)
            await websocket.close(code=1008, reason="Se esperaba el mensaje listo")
            return
        if unidad in dispositivos:
            logger.warning("ESP8266 unidad %s: ya existe un enlace", unidad)
            await websocket.close(code=4409, reason="Ya hay un enlace para esta unidad")
            return

        enlace = EnlaceDispositivo(websocket, unidad, huella)
        dispositivos[unidad] = enlace
        logger.info("ESP8266 unidad %s: listo y autenticado", unidad)
        revalidacion = asyncio.create_task(_revalidar(enlace))
        while not enlace.cerrado:
            trama = await websocket.receive()
            if trama["type"] == "websocket.disconnect":
                if not enlace.cerrado:
                    logger.info("ESP8266 unidad %s: desconectado (%s)", unidad, trama["code"])
                return
            datos = _mensaje(trama)
            if (
                datos.get("tipo") != "confirmacion" or not isinstance(datos.get("id_orden"), str)
                or type(datos.get("codigo")) is not int or type(datos.get("aplicado")) is not bool
            ):
                await enlace.cerrar(1008, "Confirmación del dispositivo inválida")
                return
            enlace.confirmar(datos["id_orden"], datos["codigo"], datos["aplicado"])
    except TimeoutError:
        logger.warning("ESP8266 unidad %s: se agotó el plazo del mensaje listo", unidad)
        await websocket.close(code=1008, reason="No se recibió listo")
    except ValueError:
        if enlace is not None:
            await enlace.cerrar(1008, "Mensaje JSON inválido")
        else:
            logger.warning("ESP8266 unidad %s: mensaje de inicio inválido", unidad)
            await websocket.close(code=1008, reason="Se esperaba JSON en el mensaje listo")
    except pymysql.MySQLError as error:
        logger.warning("ESP8266 unidad %s: no se pudo autenticar con RDS (%s)", unidad, error.args[0])
        await websocket.close(code=1011)
    except (WebSocketDisconnect, OSError, RuntimeError):
        pass
    finally:
        if revalidacion is not None:
            revalidacion.cancel()
            await asyncio.gather(revalidacion, return_exceptions=True)
        if enlace is not None:
            enlace.desconectar()
            if dispositivos.get(unidad) is enlace:
                dispositivos.pop(unidad, None)
