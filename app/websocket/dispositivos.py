import asyncio
from datetime import datetime, timezone
import logging
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect


logger = logging.getLogger("uvicorn.error.dispositivos")


class SinConfirmacion(Exception):
    pass


class EnlaceDispositivo:
    def __init__(self, websocket: WebSocket, unidad: int, huella: bytes):
        self.websocket = websocket
        self.unidad = unidad
        self.huella = huella
        self.listo_en = datetime.now(timezone.utc).replace(tzinfo=None)
        self.gestion = asyncio.Lock()
        self._escritura = asyncio.Lock()
        self._pendientes = {}
        self.cerrado = False
        self.credencial_verificada = True

    @property
    def habilitado(self):
        return not self.cerrado and self.credencial_verificada

    async def ordenar(self, codigo, duracion_ms):
        id_orden = uuid4().hex
        respuesta = asyncio.get_running_loop().create_future()
        self._pendientes[id_orden] = (codigo, respuesta)
        try:
            async with self._escritura:
                if self.cerrado:
                    raise SinConfirmacion()
                await asyncio.wait_for(
                    self.websocket.send_json({
                        "tipo": "orden", "id_orden": id_orden, "id_vehiculo": self.unidad,
                        "codigo": codigo, "duracion_ms": duracion_ms,
                    }),
                    timeout=1,
                )
            if not await asyncio.wait_for(respuesta, timeout=2):
                raise SinConfirmacion()
        except (TimeoutError, RuntimeError, OSError, WebSocketDisconnect):
            raise SinConfirmacion() from None
        finally:
            self._pendientes.pop(id_orden, None)

    def confirmar(self, id_orden, codigo, aplicado):
        pendiente = self._pendientes.get(id_orden)
        if pendiente is None:
            return
        esperado, respuesta = pendiente
        if not respuesta.done():
            respuesta.set_result(codigo == esperado and aplicado)

    def desconectar(self):
        self.cerrado = True
        for _, respuesta in self._pendientes.values():
            if not respuesta.done():
                respuesta.set_result(False)

    async def cerrar(self, codigo, motivo):
        if self.cerrado:
            return
        logger.info("ESP8266 unidad %s: cierre %s (%s)", self.unidad, codigo, motivo)
        self.desconectar()
        async with self._escritura:
            try:
                await asyncio.wait_for(self.websocket.close(code=codigo, reason=motivo), timeout=1)
            except (RuntimeError, OSError, TimeoutError, WebSocketDisconnect):
                pass


dispositivos: dict[int, EnlaceDispositivo] = {}
