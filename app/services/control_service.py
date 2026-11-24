import asyncio
from dataclasses import dataclass, field
import logging
from uuid import UUID, uuid4

import pymysql

from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.repositories.comando_repository import CODIGO_AVANZAR as AVANZAR, CODIGO_DETENER as DETENER
from app.repositories.control_repository import CODIGOS_MANTENIDOS, ControlNoAutorizado, ControlRepository
from app.schemas.demo import DEMO_MAX_TOTAL_MS
from app.websocket.dispositivos import SinConfirmacion, dispositivos
from app.websocket.manager import crear_evento, manager


DURACION_MAXIMA_MS = 250
logger = logging.getLogger("uvicorn.error.control")


@dataclass(kw_only=True)
class ControlActivo:
    detener: asyncio.Event = field(default_factory=asyncio.Event)
    motivo: str | None = None


@dataclass
class GestoControl(ControlActivo):
    codigo: int
    cambio: asyncio.Event = field(default_factory=asyncio.Event)

    def actualizar(self, codigo):
        if codigo != self.codigo and not self.detener.is_set():
            self.codigo = codigo
            self.cambio.set()


@dataclass
class Operacion:
    sesion: int
    detener: asyncio.Event
    tarea: asyncio.Task
    id_demo: int | None = None
    id_ejecucion_demo: UUID | None = None


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
        operacion = self._operaciones.get(unidad)
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
            "mantenido": bool(en_linea and enlace.continuo),
            "demo_disponible": bool(en_linea and enlace.demo_temporizada and DETENER in disponibles),
            "id_demo_activa": operacion.id_demo if operacion else None,
            "id_ejecucion_demo": operacion.id_ejecucion_demo if operacion else None,
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
            self._comprobar_prueba(enlace, sesion)
            actual = self._operaciones.get(unidad)
            if actual is not None:
                if actual.sesion != sesion and not await asyncio.to_thread(self._repo.puede_operar, unidad, sesion):
                    raise ControlNoAutorizado()
                if codigo != DETENER or (actual.sesion != sesion and actual.id_demo is None):
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
                aviso = asyncio.Event()
                tarea = asyncio.create_task(self._ciclo(unidad, sesion, enlace, aviso, codigo, id_movimiento))
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
    def _comprobar_prueba(enlace, sesion):
        if enlace.sesion_prueba_admin not in (None, sesion):
            raise ReglaNegocioError("La unidad está ocupada por una prueba de administrador")

    def en_operacion(self, unidad):
        return unidad in self._operaciones

    @staticmethod
    async def _orden_interrumpible(enlace, aviso, codigo, duracion_ms, *, continuo=False, demo=False):
        if aviso.is_set() or not enlace.habilitado:
            return False
        orden = asyncio.create_task(enlace.ordenar(codigo, duracion_ms, continuo=continuo, demo=demo))
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

    async def _ciclo(self, unidad, sesion, enlace, aviso, codigo, id_movimiento):
        confirmados = []
        try:
            reserva, catalogo = await asyncio.to_thread(
                self._repo.abrir, unidad, sesion, enlace.huella, enlace.listo_en, codigo=codigo
            )
            if codigo != DETENER and id_movimiento is not None:
                enlace.registrar_movimiento(sesion, id_movimiento)
            if codigo != DETENER and await self._orden_interrumpible(enlace, aviso, codigo, DURACION_MAXIMA_MS):
                confirmados.append(catalogo[codigo])
            if await self._detener_dispositivo(enlace, DURACION_MAXIMA_MS):
                confirmados.append(catalogo[DETENER])
            await asyncio.to_thread(self._repo.finalizar, unidad, reserva, confirmados)
            for comando in confirmados:
                await self._difundir(unidad, comando)
            codigos = {comando["codigo"] for comando in confirmados}
            return {"orden_confirmada": codigo in codigos, "detencion_confirmada": DETENER in codigos}
        finally:
            self._operaciones.pop(unidad, None)

    async def mantener(self, unidad, sesion, id_enlace, gesto, confirmar):
        enlace = dispositivos.get(unidad)
        if enlace is None or not enlace.habilitado or enlace.id_enlace != id_enlace or not enlace.continuo:
            raise ReglaNegocioError("El ESP8266 debe estar en línea con el firmware de control continuo")
        async with enlace.gestion:
            self._comprobar_prueba(enlace, sesion)
            if unidad in self._operaciones:
                raise ReglaNegocioError("Otra operación tiene la reserva de control")
            tarea = asyncio.create_task(self._ciclo_mantenido(unidad, sesion, enlace, gesto, confirmar))
            self._operaciones[unidad] = Operacion(sesion, gesto.detener, tarea)
        return await asyncio.shield(tarea)

    async def _ciclo_mantenido(self, unidad, sesion, enlace, gesto, confirmar):
        try:
            if gesto.detener.is_set():
                return {"orden_confirmada": False, "detencion_confirmada": False}
            inicial = gesto.codigo
            if inicial not in CODIGOS_MANTENIDOS or inicial not in enlace.codigos:
                raise ReglaNegocioError("El firmware conectado no admite ese movimiento")
            reserva, catalogo = await asyncio.to_thread(
                self._repo.abrir, unidad, sesion, enlace.huella, enlace.listo_en, codigo=inicial, mantenido=True
            )
            registros = asyncio.Queue()
            archivo = asyncio.create_task(self._archivar_gesto(unidad, registros, gesto))
            revision = asyncio.create_task(self._renovar_reserva(unidad, sesion, enlace, reserva, gesto))
            senal_detener = asyncio.create_task(gesto.detener.wait())
            sin_dispositivo = asyncio.create_task(enlace.desconectado.wait())
            ultimo = None
            orden_enviada = False
            detencion_confirmada = False
            try:
                while not gesto.detener.is_set() and enlace.habilitado:
                    gesto.cambio.clear()
                    codigo = gesto.codigo
                    if codigo == ultimo:
                        cambio = asyncio.create_task(gesto.cambio.wait())
                        try:
                            await asyncio.wait((cambio, senal_detener, sin_dispositivo),
                                               return_when=asyncio.FIRST_COMPLETED)
                        finally:
                            cambio.cancel()
                            await asyncio.gather(cambio, return_exceptions=True)
                        continue
                    if codigo not in catalogo or codigo not in enlace.codigos:
                        raise ReglaNegocioError("La dirección no está habilitada para esta unidad")
                    orden_enviada = True
                    aplicada = await self._orden_interrumpible(enlace, gesto.detener, codigo, 0, continuo=True)
                    if not aplicada:
                        if not gesto.detener.is_set():
                            gesto.motivo = "No se confirmó la orden en el ESP8266"
                        break
                    ultimo = codigo
                    registros.put_nowait(catalogo[codigo])
                    if not gesto.detener.is_set():
                        await confirmar("movimiento_aplicado", codigo)
                if not gesto.detener.is_set() and not enlace.habilitado:
                    gesto.motivo = "Se perdió el enlace disponible con el ESP8266"
            except ReglaNegocioError as error:
                gesto.motivo = str(error)
            finally:
                gesto.detener.set()
                try:
                    if orden_enviada:
                        detencion_confirmada = await self._detener_dispositivo(enlace, 0)
                finally:
                    revision.cancel()
                    sin_dispositivo.cancel()
                    registros.put_nowait(None)
                    try:
                        if detencion_confirmada:
                            await confirmar("detencion_aplicada", DETENER)
                    finally:
                        try:
                            await asyncio.gather(revision, senal_detener, sin_dispositivo, return_exceptions=True)
                            await archivo
                        finally:
                            paradas = [catalogo[DETENER]] if detencion_confirmada else []
                            await asyncio.to_thread(self._repo.finalizar, unidad, reserva, paradas)
                            if paradas:
                                await self._difundir(unidad, paradas[0])
            if orden_enviada and not detencion_confirmada and not gesto.motivo:
                gesto.motivo = "El ESP8266 no confirmó DETENER"
            if gesto.motivo:
                logger.info("Unidad %s: %s", unidad, gesto.motivo)
                raise ReglaNegocioError(gesto.motivo)
            return {"orden_confirmada": ultimo is not None, "detencion_confirmada": detencion_confirmada}
        finally:
            self._operaciones.pop(unidad, None)

    async def iniciar_demo(self, unidad, sesion, id_demo, id_enlace):
        enlace = dispositivos.get(unidad)
        if enlace is None or not enlace.habilitado or enlace.id_enlace != id_enlace or not enlace.demo_temporizada:
            if not await asyncio.to_thread(self._repo.puede_operar, unidad, sesion):
                raise ControlNoAutorizado()
            raise ReglaNegocioError("Conecta el ESP8266 con el sketch actualizado para demos")
        async with enlace.gestion:
            self._comprobar_prueba(enlace, sesion)
            if unidad in self._operaciones:
                if not await asyncio.to_thread(self._repo.puede_operar, unidad, sesion):
                    raise ControlNoAutorizado()
                raise ReglaNegocioError("Otra operación tiene la reserva de control")
            activo = ControlActivo()
            id_ejecucion = uuid4()
            aceptada = asyncio.get_running_loop().create_future()
            tarea = asyncio.create_task(self._ciclo_demo(
                unidad, sesion, enlace, id_demo, id_ejecucion, activo, aceptada
            ))
            self._operaciones[unidad] = Operacion(sesion, activo.detener, tarea, id_demo, id_ejecucion)
        resultado = await asyncio.shield(aceptada)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado

    async def cancelar_demo(self, unidad, sesion):
        enlace = dispositivos.get(unidad)
        if enlace is not None:
            self._comprobar_prueba(enlace, sesion)
        operacion = self._operaciones.get(unidad)
        if operacion is None or operacion.sesion != sesion:
            if not await asyncio.to_thread(self._repo.puede_operar, unidad, sesion):
                raise ControlNoAutorizado()
        if operacion is None or operacion.id_demo is None:
            raise RecursoNoEncontradoError("No hay una demo en ejecución para esta unidad")
        operacion.detener.set()
        resultado = await asyncio.shield(operacion.tarea)
        return resultado["detencion_confirmada"]

    def detener_demo_de_sesion(self, unidad, sesion):
        operacion = self._operaciones.get(unidad)
        if operacion is not None and operacion.id_demo is not None and operacion.sesion == sesion:
            operacion.detener.set()

    async def detener_demos(self):
        operaciones = [op for op in self._operaciones.values() if op.id_demo is not None]
        for op in operaciones:
            op.detener.set()
        await asyncio.gather(*(op.tarea for op in operaciones), return_exceptions=True)

    async def _ciclo_demo(self, unidad, sesion, enlace, id_demo, id_ejecucion, activo, aceptada):
        operacion = self._operaciones[unidad]
        detencion = False
        try:
            try:
                reserva, catalogo, pasos = await asyncio.to_thread(
                    self._repo.abrir_demo, unidad, sesion, enlace.huella, enlace.listo_en, id_demo, enlace.codigos
                )
            except Exception as error:
                aceptada.set_result(error)
                return {"orden_confirmada": False, "detencion_confirmada": False}

            aceptada.set_result({"id_vehiculo": unidad, "id_demo": id_demo, "id_ejecucion": id_ejecucion,
                                 "total_movimientos": len(pasos), "mensaje": "Demo aceptada"})
            eventos = asyncio.Queue()
            publicacion = asyncio.create_task(self._publicar_demo(unidad, eventos, activo))
            revision = asyncio.create_task(self._renovar_reserva(unidad, sesion, enlace, reserva, activo))
            desconexion = asyncio.create_task(self._vigilar_enlace_demo(enlace, activo))
            datos = {"id_demo": id_demo, "id_ejecucion": str(id_ejecucion)}
            eventos.put_nowait((crear_evento("demo_inicio", unidad, total_movimientos=len(pasos), **datos), None))
            try:
                async with asyncio.timeout(DEMO_MAX_TOTAL_MS / 1000 + 5):
                    for paso in pasos:
                        if activo.detener.is_set():
                            break
                        codigo = paso["codigo"]
                        aplicado = await self._orden_interrumpible(
                            enlace, activo.detener, codigo, paso["duracion_ms"] if codigo != DETENER else 0,
                            demo=codigo != DETENER,
                        )
                        if not aplicado:
                            if not activo.detener.is_set():
                                activo.motivo = "El ESP8266 no confirmó el paso"
                            break
                        evento = crear_evento("demo_movimiento", unidad, comando=paso["nombre"], codigo=codigo,
                                              orden=paso["orden"], duracion_ms=paso["duracion_ms"],
                                              pausa_ms=paso["pausa_ms"], **datos)
                        eventos.put_nowait((evento, paso["id_comando"]))
                        await self._esperar_paso(activo.detener, paso["duracion_ms"] + paso["pausa_ms"])
            except TimeoutError:
                activo.motivo = "Se agotó el tiempo de ejecución de la demo"
            except Exception:
                logger.exception("Error durante la demo en la unidad %s", unidad)
                activo.motivo = "Ocurrió un error durante la ejecución de la demo"
            finally:
                try:
                    detencion = await self._detener_dispositivo(enlace, 0)
                finally:
                    revision.cancel()
                    desconexion.cancel()
                    eventos.put_nowait(None)
                    try:
                        await asyncio.gather(revision, desconexion, return_exceptions=True)
                        await publicacion
                        if detencion:
                            await asyncio.to_thread(self._repo.estado_demo, unidad, catalogo[DETENER]["id_comando"])
                    except pymysql.MySQLError:
                        activo.motivo = "La base de datos no pudo guardar el estado de la demo"
                    finally:
                        try:
                            await asyncio.to_thread(self._repo.finalizar, unidad, reserva, [])
                        except pymysql.MySQLError:
                            logger.exception("No se pudo cerrar la reserva de la demo en la unidad %s", unidad)
                            activo.motivo = "La base de datos no pudo liberar la reserva de la demo"
                        if not detencion:
                            activo.motivo = "El ESP8266 no confirmó DETENER"
                        tipo = ("demo_error" if activo.motivo else
                                "demo_cancelada" if activo.detener.is_set() else "demo_fin")
                        self._operaciones.pop(unidad, None)
                        await manager.difundir(unidad, crear_evento(
                            tipo, unidad, comando=catalogo[DETENER]["nombre"] if detencion else None,
                            codigo=DETENER if detencion else None, detencion_confirmada=detencion,
                            mensaje=activo.motivo, **datos,
                        ))
            return {"orden_confirmada": detencion, "detencion_confirmada": detencion}
        finally:
            if self._operaciones.get(unidad) is operacion:
                self._operaciones.pop(unidad, None)

    @staticmethod
    async def _vigilar_enlace_demo(enlace, activo):
        await enlace.desconectado.wait()
        activo.motivo = "Se perdió el enlace con el ESP8266 durante la demo"
        activo.detener.set()

    @staticmethod
    async def _esperar_paso(detener, tiempo_ms):
        try:
            await asyncio.wait_for(detener.wait(), timeout=tiempo_ms / 1000)
        except TimeoutError:
            pass

    async def _publicar_demo(self, unidad, eventos, activo):
        while (registro := await eventos.get()) is not None:
            evento, comando = registro
            try:
                if comando is not None:
                    await asyncio.to_thread(self._repo.estado_demo, unidad, comando)
                await manager.difundir(unidad, evento)
            except Exception:
                logger.exception("Error al actualizar Monitoreo de la demo en la unidad %s", unidad)
                activo.motivo = "No se pudo actualizar el estado de la demo"
                activo.detener.set()

    async def _renovar_reserva(self, unidad, sesion, enlace, reserva, gesto):
        while not gesto.detener.is_set():
            await asyncio.sleep(4)
            for intento in range(2):
                if gesto.detener.is_set():
                    return
                try:
                    vigente = await asyncio.wait_for(asyncio.to_thread(
                        self._repo.renovar_reserva, unidad, sesion, enlace.huella, reserva
                    ), timeout=4)
                    break
                except (TimeoutError, pymysql.MySQLError):
                    vigente = False
                    if intento == 0:
                        await asyncio.sleep(0.5)
            if not vigente:
                gesto.motivo = "RDS no pudo revalidar la reserva de control"
                gesto.detener.set()
                return

    async def _archivar_gesto(self, unidad, registros, gesto):
        try:
            while (primero := await registros.get()) is not None:
                lote = [primero]
                ultimo_lote = False
                while not registros.empty():
                    siguiente = registros.get_nowait()
                    if siguiente is None:
                        ultimo_lote = True
                        break
                    lote.append(siguiente)
                await asyncio.to_thread(self._repo.registrar, unidad, lote)
                await self._difundir(unidad, lote[-1])
                if ultimo_lote:
                    return
        except Exception:
            gesto.detener.set()
            raise

    @staticmethod
    async def _detener_dispositivo(enlace, duracion_ms):
        try:
            await enlace.ordenar(DETENER, 0)
        except SinConfirmacion:
            await enlace.cerrar(1011, "Sin confirmación de DETENER")
            await asyncio.sleep(duracion_ms / 1000)
            return False
        return True

    @staticmethod
    async def _difundir(unidad, comando):
        await manager.difundir(unidad, crear_evento(
            "movimiento", unidad, comando=comando["nombre"], codigo=comando["codigo"], origen="CONTROL_4_3"
        ))


control = ControlService()
