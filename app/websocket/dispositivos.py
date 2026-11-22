import asyncio
from datetime import datetime, timezone
import logging
from time import monotonic
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect


logger = logging.getLogger("uvicorn.error.dispositivos")


class SinConfirmacion(Exception):
    pass


class EnlaceDispositivo:
    def __init__(self, websocket: WebSocket, unidad: int, huella: bytes, codigos: frozenset[int],
                 *, continuo=False, demo_temporizada=False):
        self.websocket = websocket
        self.unidad = unidad
        self.huella = huella
        self.codigos = codigos
        self.continuo = continuo
        self.demo_temporizada = demo_temporizada
        self.id_enlace = uuid4()
        self.listo_en = datetime.now(timezone.utc).replace(tzinfo=None)
        self.gestion = asyncio.Lock()
        self._escritura = asyncio.Lock()
        self._pendientes = {}
        self._movimientos = {}
        self.cerrado = False
        self.desconectado = asyncio.Event()
        self.credencial_verificada = True

    @property
    def habilitado(self):
        return not self.cerrado and self.credencial_verificada

    def registrar_movimiento(self, sesion, id_movimiento):
        ahora = monotonic()
        self._movimientos = {orden: vence for orden, vence in self._movimientos.items() if vence > ahora}
        self._movimientos[sesion, id_movimiento] = ahora + 45

    def movimiento_registrado(self, sesion, id_movimiento):
        return self._movimientos.get((sesion, id_movimiento), 0) > monotonic()

    async def _enviar(self, trama, timeout):
        try:
            async with self._escritura:
                if self.cerrado:
                    raise SinConfirmacion()
                await asyncio.wait_for(self.websocket.send_json(trama), timeout=timeout)
        except (TimeoutError, RuntimeError, OSError, WebSocketDisconnect):
            raise SinConfirmacion() from None

    async def ordenar(self, codigo, duracion_ms, *, continuo=False, demo=False):
        id_orden = uuid4().hex
        respuesta = asyncio.get_running_loop().create_future()
        self._pendientes[id_orden] = (codigo, respuesta)
        tipo = "orden_demo" if demo else "mando_continuo" if continuo else "orden"
        trama = {
            "tipo": tipo, "id_orden": id_orden, "id_vehiculo": self.unidad,
            "codigo": codigo, "duracion_ms": duracion_ms,
        }
        try:
            await self._enviar(trama, timeout=1)
            if not await asyncio.wait_for(respuesta, timeout=2):
                raise SinConfirmacion()
        except TimeoutError:
            raise SinConfirmacion() from None
        finally:
            self._pendientes.pop(id_orden, None)

    def confirmar(self, id_orden, codigo, aplicado):
        pendiente = self._pendientes.get(id_orden)
        if pendiente is not None:
            esperado, respuesta = pendiente
            if not respuesta.done():
                respuesta.set_result(codigo == esperado and aplicado)

    def desconectar(self):
        self.cerrado = True
        self.desconectado.set()
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
