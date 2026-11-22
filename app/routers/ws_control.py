import asyncio
from typing import Annotated, Literal

import pymysql
from fastapi import APIRouter, Path, WebSocket, WebSocketDisconnect, WebSocketException
from pydantic import BaseModel, ConfigDict, StrictInt, UUID4, ValidationError

from app.config import ORIGENES_CLIENTE
from app.exceptions import ReglaNegocioError
from app.repositories.control_repository import CODIGOS_MANTENIDOS, ControlNoAutorizado
from app.routers.ws_autenticado import _autenticar
from app.services.control_service import GestoControl, control


router = APIRouter()


class OrdenJoystick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["iniciar", "cambiar", "soltar"]
    id_gesto: UUID4
    id_enlace: UUID4 | None = None
    codigo: StrictInt | None = None


@router.websocket("/ws/control/{unidad}")
async def controlar_joystick(websocket: WebSocket, unidad: Annotated[int, Path(gt=0, le=2**31 - 1)]):
    if websocket.headers.get("origin") not in ORIGENES_CLIENTE:
        await websocket.close(1008, "Origen no permitido")
        return

    await websocket.accept()
    abierto = True
    envio = asyncio.Lock()
    gesto = None
    id_activo = None
    tarea = None

    async def enviar(tipo, **datos):
        if not abierto:
            return
        async with envio:
            if abierto:
                await asyncio.wait_for(websocket.send_json({"tipo": tipo, **datos}), 0.5)

    async def ejecutar(orden, sesion, activo):
        identificador = str(orden.id_gesto)

        async def confirmar(tipo, codigo):
            await enviar(tipo, id_gesto=identificador, codigo=codigo)

        try:
            await control.mantener(unidad, sesion.id_sesion, orden.id_enlace, activo, confirmar)
        except ReglaNegocioError as error:
            await enviar("error", id_gesto=identificador, mensaje=str(error))
        except ControlNoAutorizado:
            await enviar("error", id_gesto=identificador, mensaje="La unidad ya no está asignada a tu sesión")
        except pymysql.MySQLError:
            await enviar("error", id_gesto=identificador, mensaje="RDS no respondió al control de esta unidad")
        finally:
            try:
                await enviar("fin", id_gesto=identificador)
            except (RuntimeError, WebSocketDisconnect, TimeoutError, OSError):
                activo.detener.set()

    try:
        sesion = await _autenticar(websocket)
        if sesion.usuario.rol != "usuario":
            raise WebSocketException(4403, "Se requiere una sesión de comprador")
        await control.estado(unidad, sesion.id_sesion)
        await enviar("listo")
        while True:
            trama = await websocket.receive()
            if trama["type"] == "websocket.disconnect":
                break
            mensaje = trama.get("text")
            if not isinstance(mensaje, str) or len(mensaje) > 512:
                raise WebSocketException(1008, "Orden inválida")
            orden = OrdenJoystick.model_validate_json(mensaje)
            if orden.tipo != "soltar" and orden.codigo not in CODIGOS_MANTENIDOS:
                raise WebSocketException(1008, "La dirección no es un mando mantenido")
            if orden.tipo == "iniciar":
                if orden.id_enlace is None:
                    raise WebSocketException(1008, "Indica el enlace del ESP8266")
                if tarea is not None and not tarea.done():
                    await enviar("error", id_gesto=str(orden.id_gesto), mensaje="El control anterior sigue cerrándose")
                    await enviar("fin", id_gesto=str(orden.id_gesto))
                    continue
                gesto = GestoControl(orden.codigo)
                id_activo = orden.id_gesto
                tarea = asyncio.create_task(ejecutar(orden, sesion, gesto))
            elif gesto is not None and orden.id_gesto == id_activo:
                if orden.tipo == "soltar":
                    gesto.detener.set()
                else:
                    gesto.actualizar(orden.codigo)
    except ControlNoAutorizado:
        await websocket.close(4403, "La unidad no está asignada a la sesión")
    except pymysql.MySQLError:
        await websocket.close(1011, "Base de datos no disponible")
    except ValidationError:
        await websocket.close(1008, "Orden inválida")
    except WebSocketException as error:
        await websocket.close(error.code, error.reason)
    except (WebSocketDisconnect, RuntimeError, TimeoutError, OSError):
        pass
    finally:
        abierto = False
        if gesto is not None:
            gesto.detener.set()
        if tarea is not None:
            await asyncio.gather(tarea, return_exceptions=True)
