import asyncio
from dataclasses import dataclass

import pymysql

from app.exceptions import ReglaNegocioError
from app.repositories.control_repository import ControlNoAutorizado, ControlRepository
from app.websocket.dispositivos import SinConfirmacion, dispositivos
from app.websocket.manager import crear_evento, manager


AVANZAR = 1
DETENER = 9
DURACION_MAXIMA_MS = 250


@dataclass
class Operacion:
    sesion: int
    detener: asyncio.Event
    tarea: asyncio.Task


class ControlService:
    def __init__(self):
        self._repo = ControlRepository()
        self._operaciones: dict[int, Operacion] = {}

    async def estado(self, unidad, sesion):
        enlace = dispositivos.get(unidad)
        huella = enlace.huella if enlace is not None and enlace.habilitado else None
        vigente = await asyncio.to_thread(self._repo.estado_control, unidad, sesion, huella)
        return bool(vigente and enlace and enlace.habilitado and dispositivos.get(unidad) is enlace)

    async def ejecutar(self, unidad, sesion, *, avanzar):
        enlace = dispositivos.get(unidad)
        if enlace is None or not enlace.habilitado:
            if not await asyncio.to_thread(self._repo.puede_operar, unidad, sesion):
                raise ControlNoAutorizado()
            if enlace and not enlace.cerrado:
                raise ReglaNegocioError("La verificación del dispositivo con RDS está en pausa")
            raise ReglaNegocioError("El dispositivo no está conectado")
        async with enlace.gestion:
            actual = self._operaciones.get(unidad)
            if actual is not None:
                if actual.sesion != sesion and not await asyncio.to_thread(self._repo.puede_operar, unidad, sesion):
                    raise ControlNoAutorizado()
                if avanzar or actual.sesion != sesion:
                    raise ReglaNegocioError("Otra operación tiene la reserva de control")
                actual.detener.set()
                tarea = actual.tarea
            else:
                if not enlace.habilitado or dispositivos.get(unidad) is not enlace:
                    raise ReglaNegocioError("El dispositivo dejó de estar disponible para control")
                reserva, catalogo = await asyncio.to_thread(
                    self._repo.abrir, unidad, sesion, enlace.huella, enlace.listo_en, avanzar=avanzar
                )
                aviso = asyncio.Event()
                tarea = asyncio.create_task(self._ciclo(unidad, sesion, enlace, reserva, catalogo, aviso, avanzar))
                self._operaciones[unidad] = Operacion(sesion, aviso, tarea)
        return await asyncio.shield(tarea)

    def detener_sesion(self, id_sesion):
        for operacion in self._operaciones.values():
            if operacion.sesion == id_sesion:
                operacion.detener.set()

    @staticmethod
    async def _pulsar(enlace, aviso):
        if aviso.is_set() or not enlace.habilitado:
            return False
        orden = asyncio.create_task(enlace.ordenar(AVANZAR, DURACION_MAXIMA_MS))
        detener = asyncio.create_task(aviso.wait())
        try:
            terminadas, _ = await asyncio.wait((orden, detener), return_when=asyncio.FIRST_COMPLETED)
            if orden not in terminadas:
                return False
            await orden
            return True
        except SinConfirmacion:
            return False
        finally:
            for tarea in (orden, detener):
                if not tarea.done():
                    tarea.cancel()
            await asyncio.gather(orden, detener, return_exceptions=True)

    async def _ciclo(self, unidad, sesion, enlace, reserva, catalogo, aviso, avanzar):
        confirmados = []
        error_acceso = None
        try:
            if avanzar:
                try:
                    permitido = await asyncio.to_thread(self._repo.puede_operar, unidad, sesion)
                except pymysql.MySQLError as error:
                    permitido = False
                    error_acceso = error
                if permitido and await self._pulsar(enlace, aviso):
                    confirmados.append(catalogo[AVANZAR])
            try:
                await enlace.ordenar(DETENER, 0)
                confirmados.append(catalogo[DETENER])
            except SinConfirmacion:
                await enlace.cerrar(1011, "Sin confirmación de DETENER")
                # Tras perder la conexión el firmware también limita el pulso local.
                await asyncio.sleep(DURACION_MAXIMA_MS / 1000)

            await asyncio.to_thread(self._repo.finalizar, unidad, reserva, confirmados)
            for comando in confirmados:
                await manager.difundir(unidad, crear_evento(
                    "movimiento", unidad, comando=comando["nombre"], codigo=comando["codigo"], origen="CONTROL_4_3"
                ))
            if error_acceso is not None:
                raise error_acceso
            codigos = {comando["codigo"] for comando in confirmados}
            return {"avance_confirmado": AVANZAR in codigos, "detencion_confirmada": DETENER in codigos}
        finally:
            self._operaciones.pop(unidad, None)


control = ControlService()
