import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect, WebSocketException


def crear_evento(evento, id_vehiculo, comando=None, codigo=None, **extra):
    return {
        "evento": evento,
        "id_vehiculo": id_vehiculo,
        "comando": comando,
        "codigo": codigo,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


def evento_estado_actual(id_vehiculo, estado):
    return crear_evento(
        "estado_actual",
        id_vehiculo,
        comando=estado["comando"] if estado else None,
        codigo=estado["codigo"] if estado else None,
        conectado=bool(estado["conectado"]) if estado else False,
    )


class Suscripcion:
    def __init__(
        self,
        websocket: WebSocket,
        id_sesion: int | None = None,
        autorizar: Callable[[dict | None], Awaitable[bool]] | None = None,
    ):
        self.websocket = websocket
        self.id_sesion = id_sesion
        self._autorizar = autorizar
        self._envio = asyncio.Lock()
        self._cerrada = False

    async def enviar_o_revalidar(self, mensaje: dict | None = None):
        async with self._envio:
            if self._cerrada:
                return False
            try:
                permitido = self._autorizar is None or await self._autorizar(mensaje)
                if mensaje is not None and permitido:
                    await asyncio.wait_for(self.websocket.send_json(mensaje), timeout=3)
            except WebSocketException as error:
                await self._cerrar(error.code, error.reason)
            except (TimeoutError, WebSocketDisconnect, RuntimeError, OSError):
                await self._cerrar(1011, "No se pudo entregar el evento")
            return not self._cerrada

    async def cerrar(self, codigo, motivo):
        async with self._envio:
            await self._cerrar(codigo, motivo)

    async def _cerrar(self, codigo, motivo):
        if self._cerrada:
            return
        self._cerrada = True
        try:
            await asyncio.wait_for(self.websocket.close(code=codigo, reason=motivo), timeout=3)
        except (TimeoutError, WebSocketDisconnect, RuntimeError, OSError):
            pass


class ConnectionManager:
    def __init__(self):
        self._conexiones: dict[int, dict[WebSocket, Suscripcion]] = {}

    def agregar(self, id_vehiculo: int, suscripcion: Suscripcion):
        self._conexiones.setdefault(id_vehiculo, {})[suscripcion.websocket] = suscripcion

    def quitar(self, id_vehiculo: int, websocket: WebSocket):
        conexiones = self._conexiones.get(id_vehiculo)
        if conexiones is not None:
            conexiones.pop(websocket, None)
        if not conexiones:
            self._conexiones.pop(id_vehiculo, None)

    async def difundir(self, id_vehiculo: int, mensaje: dict):
        if mensaje.get("id_vehiculo") != id_vehiculo:
            raise ValueError("El evento no corresponde al vehículo del canal")
        await self._verificar_conexiones(id_vehiculo, mensaje)

    async def revalidar_unidad(self, id_vehiculo: int):
        await self._verificar_conexiones(id_vehiculo)

    async def _verificar_conexiones(self, id_vehiculo, mensaje=None):
        conexiones = tuple(self._conexiones.get(id_vehiculo, {}).values())
        resultados = await asyncio.gather(*(canal.enviar_o_revalidar(mensaje) for canal in conexiones))
        for canal, sigue_abierto in zip(conexiones, resultados):
            if not sigue_abierto:
                self.quitar(id_vehiculo, canal.websocket)

    async def cerrar_sesion(self, id_sesion: int):
        canales = [
            (id_vehiculo, canal)
            for id_vehiculo, conexiones in self._conexiones.items()
            for canal in conexiones.values() if canal.id_sesion == id_sesion
        ]
        await asyncio.gather(*(canal.cerrar(4401, "Sesión finalizada") for _, canal in canales))
        for id_vehiculo, canal in canales:
            self.quitar(id_vehiculo, canal.websocket)


manager = ConnectionManager()
