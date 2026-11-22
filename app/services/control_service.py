import asyncio
from dataclasses import dataclass

import pymysql

from app.exceptions import ReglaNegocioError
from app.repositories.comando_repository import CODIGO_AVANZAR as AVANZAR, CODIGO_DETENER as DETENER
from app.repositories.control_repository import ControlNoAutorizado, ControlRepository
from app.websocket.dispositivos import SinConfirmacion, dispositivos
from app.websocket.manager import crear_evento, manager


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
        vigente, codigos = await asyncio.to_thread(self._repo.estado_control, unidad, sesion, huella)
        en_linea = bool(vigente and enlace and enlace.habilitado and dispositivos.get(unidad) is enlace)
        disponibles = codigos & enlace.codigos if en_linea else set()
        if DETENER not in disponibles:
            disponibles.clear()
        acciones = []
        if DETENER in disponibles:
            acciones.append("detener")
            if AVANZAR in disponibles:
                acciones.append("avanzar")
        return {
            "dispositivo_en_linea": en_linea,
            "maximo_avance_ms": DURACION_MAXIMA_MS,
            "acciones_habilitadas": acciones,
            "codigos_habilitados": sorted(disponibles),
            "id_enlace": enlace.id_enlace if en_linea else None,
        }

    async def ejecutar(self, unidad, sesion, *, codigo, id_enlace=None, id_movimiento=None):
        enlace = dispositivos.get(unidad)
        if enlace is None or not enlace.habilitado or (id_enlace is not None and enlace.id_enlace != id_enlace):
            if not await asyncio.to_thread(self._repo.puede_operar, unidad, sesion):
                raise ControlNoAutorizado()
            if enlace and enlace.habilitado:
                raise ReglaNegocioError("La conexión del dispositivo cambió. Intenta de nuevo")
            if enlace and not enlace.cerrado:
                raise ReglaNegocioError("La verificación del dispositivo con RDS está en pausa")
            raise ReglaNegocioError("El dispositivo no está conectado")
        if codigo not in enlace.codigos:
            if not await asyncio.to_thread(self._repo.puede_operar, unidad, sesion):
                raise ControlNoAutorizado()
            raise ReglaNegocioError("El firmware conectado no admite ese comando")
        async with enlace.gestion:
            actual = self._operaciones.get(unidad)
            if actual is not None:
                if actual.sesion != sesion and not await asyncio.to_thread(self._repo.puede_operar, unidad, sesion):
                    raise ControlNoAutorizado()
                if codigo != DETENER or actual.sesion != sesion:
                    raise ReglaNegocioError("Otra operación tiene la reserva de control")
                if id_movimiento is not None:
                    enlace.registrar_movimiento(sesion, id_movimiento)
                actual.detener.set()
                tarea = actual.tarea
            else:
                if not enlace.habilitado or dispositivos.get(unidad) is not enlace:
                    raise ReglaNegocioError("El dispositivo dejó de estar disponible para control")
                if id_movimiento is not None:
                    if codigo == DETENER:
                        if not await asyncio.to_thread(self._repo.puede_operar, unidad, sesion):
                            raise ControlNoAutorizado()
                        enlace.registrar_movimiento(sesion, id_movimiento)
                    elif enlace.movimiento_registrado(sesion, id_movimiento):
                        raise ReglaNegocioError("El movimiento ya se procesó o se canceló con DETENER")
                reserva, catalogo = await asyncio.to_thread(
                    self._repo.abrir, unidad, sesion, enlace.huella, enlace.listo_en, codigo=codigo
                )
                if codigo != DETENER and id_movimiento is not None:
                    enlace.registrar_movimiento(sesion, id_movimiento)
                aviso = asyncio.Event()
                tarea = asyncio.create_task(self._ciclo(unidad, sesion, enlace, reserva, catalogo, aviso, codigo))
                self._operaciones[unidad] = Operacion(sesion, aviso, tarea)
        resultado = await asyncio.shield(tarea)
        if codigo == DETENER:
            return {**resultado, "orden_confirmada": resultado["detencion_confirmada"]}
        return resultado

    def detener_sesion(self, id_sesion):
        for operacion in self._operaciones.values():
            if operacion.sesion == id_sesion:
                operacion.detener.set()

    @staticmethod
    async def _pulsar(enlace, aviso, codigo):
        if aviso.is_set() or not enlace.habilitado:
            return False
        orden = asyncio.create_task(enlace.ordenar(codigo, DURACION_MAXIMA_MS))
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

    async def _ciclo(self, unidad, sesion, enlace, reserva, catalogo, aviso, codigo):
        confirmados = []
        error_acceso = None
        try:
            if codigo != DETENER:
                try:
                    permitido = await asyncio.to_thread(self._repo.puede_operar, unidad, sesion)
                except pymysql.MySQLError as error:
                    permitido = False
                    error_acceso = error
                if permitido and await self._pulsar(enlace, aviso, codigo):
                    confirmados.append(catalogo[codigo])
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
            return {"orden_confirmada": codigo in codigos, "detencion_confirmada": DETENER in codigos}
        finally:
            self._operaciones.pop(unidad, None)


control = ControlService()
