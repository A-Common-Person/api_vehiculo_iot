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
from app.services.exhibicion_service import exhibir
from app.websocket.dispositivos import dispositivos


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
    prueba = None

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
        await control.estado(unidad, sesion.id_sesion)
        if sesion.usuario.rol == "administrador":
            enlace = dispositivos.get(unidad)
            if not enlace or not enlace.habilitado:
                raise WebSocketException(4410, "La unidad está desconectada")
            async with enlace.gestion:
                if exhibir.ocupada(unidad) or control.en_operacion(unidad) or enlace.sesion_prueba_admin is not None:
                    raise WebSocketException(4409, "La unidad está ocupada")
                enlace.sesion_prueba_admin = sesion.id_sesion
                prueba = enlace
        await enviar("listo")
        reloj = asyncio.get_running_loop()
        verificar_en = reloj.time() + 5
        while True:
            if prueba is None:
                trama = await websocket.receive()
            else:
                if reloj.time() >= verificar_en:
                    if dispositivos.get(unidad) is not prueba:
                        raise WebSocketException(4410, "El dispositivo se desconectó")
                    await control.estado(unidad, sesion.id_sesion)
                    verificar_en = reloj.time() + 5
                try:
                    trama = await asyncio.wait_for(websocket.receive(), verificar_en - reloj.time())
                except TimeoutError:
                    continue
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
        if prueba is not None:
            control.detener_demo_de_sesion(unidad, sesion.id_sesion)
            prueba.sesion_prueba_admin = None
        if gesto is not None:
            gesto.detener.set()
        if tarea is not None:
            await asyncio.gather(tarea, return_exceptions=True)
