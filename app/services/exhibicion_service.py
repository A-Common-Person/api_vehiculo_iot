import asyncio
from dataclasses import dataclass, field
from hashlib import sha256
import logging
from secrets import token_urlsafe
from time import monotonic

import pymysql

from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.repositories.comando_repository import CODIGO_DETENER
from app.repositories.exhibicion_repository import ExhibicionRepository
from app.schemas.demo import DEMO_MIN_PASO_MS
from app.schemas.exhibicion import CODIGOS_EXHIBICION, DURACION_EXHIBICION_S, MOVIMIENTO_EXHIBICION_MS
from app.services.autenticacion_service import FORMATO_TOKEN
from app.websocket.dispositivos import EnlaceDispositivo, SinConfirmacion, dispositivos


logger = logging.getLogger("uvicorn.error.exhibicion")
VIGENCIA_CANAL_S = 6
INTERVALO_MANDOS_S = 0.75


@dataclass
class ReservaInvitado:
    id: int
    unidad: int
    huella: bytes
    enlace: EnlaceDispositivo
    mandos: dict[int, int]
    vence: float
    ultimo_contacto: float = field(default_factory=monotonic)
    motivo: str | None = None
    canal: bool = False
    proximo_pulso: float = 0
    cerrar: asyncio.Event = field(default_factory=asyncio.Event)
    finalizada: asyncio.Event = field(default_factory=asyncio.Event)
    cerro_reserva: bool = False
    confirmo_detener: bool = False
    movimiento: asyncio.Task | None = None
    vigilancia: asyncio.Task | None = None
    mando: asyncio.Lock = field(default_factory=asyncio.Lock)

    def terminar(self, motivo):
        if not self.cerrar.is_set():
            self.motivo = motivo
            self.cerrar.set()

    def segundos(self):
        return max(0, int(self.vence - monotonic() + 0.999))


class ExhibicionService:
    def __init__(self):
        self._repo = ExhibicionRepository()
        self._reservas: dict[bytes, ReservaInvitado] = {}
        self._por_unidad: dict[int, ReservaInvitado] = {}

    @staticmethod
    def _admite_exhibicion(enlace):
        return enlace is not None and enlace.habilitado and enlace.demo_temporizada

    async def catalogo(self):
        modelos = await asyncio.to_thread(self._repo.catalogo)
        for modelo in modelos:
            for unidad in modelo["unidades"]:
                id_vehiculo = unidad["id_vehiculo"]
                enlace = dispositivos.get(id_vehiculo)
                previa = unidad.pop("vence_en")
                permitidos = unidad.pop("codigos")
                if (id_vehiculo in self._por_unidad or (enlace and enlace.sesion_prueba_admin is not None)
                        or (previa and (not enlace or enlace.listo_en < previa))):
                    disponibilidad = "ocupada"
                elif not self._admite_exhibicion(enlace):
                    disponibilidad = "sin_conexion"
                elif CODIGO_DETENER not in permitidos or len(permitidos & enlace.codigos) < 2:
                    disponibilidad = "sin_configurar"
                else:
                    disponibilidad = "disponible"
                unidad["disponibilidad"] = disponibilidad
        return modelos

    async def reservar(self, unidad):
        if not await asyncio.to_thread(self._repo.publica, unidad):
            raise RecursoNoEncontradoError("La unidad no está en exhibición")
        enlace = dispositivos.get(unidad)
        if not self._admite_exhibicion(enlace):
            raise ReglaNegocioError("La prueba de esta unidad no está disponible")
        async with enlace.gestion:
            if unidad in self._por_unidad or enlace.sesion_prueba_admin is not None:
                raise ReglaNegocioError("La unidad está ocupada")
            token = token_urlsafe(32)
            huella = sha256(token.encode("ascii")).digest()
            vence = monotonic() + DURACION_EXHIBICION_S
            id_reserva, mandos = await asyncio.to_thread(self._repo.abrir, unidad, huella, enlace, DURACION_EXHIBICION_S)
            reserva = ReservaInvitado(id_reserva, unidad, huella, enlace, mandos, vence)
            self._reservas[huella] = reserva
            self._por_unidad[unidad] = reserva
            reserva.vigilancia = asyncio.create_task(self._vigilar(reserva))
            return {"token": token, "id_vehiculo": unidad, "segundos": reserva.segundos(),
                    "comandos": [{"codigo": c, "nombre": CODIGOS_EXHIBICION[c]} for c in sorted(mandos)]}

    def identificar(self, token):
        if not FORMATO_TOKEN.fullmatch(token):
            return None
        return self._reservas.get(sha256(token.encode("ascii")).digest())

    def ocupada(self, unidad):
        return unidad in self._por_unidad

    async def _vigilar(self, reserva):
        enlace_perdido = asyncio.create_task(reserva.enlace.desconectado.wait())
        cierre = asyncio.create_task(reserva.cerrar.wait())
        try:
            while not reserva.cerrar.is_set():
                ahora = monotonic()
                if ahora >= reserva.vence:
                    reserva.terminar("tiempo_agotado")
                elif enlace_perdido.done() or not self._admite_exhibicion(reserva.enlace):
                    reserva.terminar("dispositivo_desconectado")
                elif ahora - reserva.ultimo_contacto >= VIGENCIA_CANAL_S:
                    reserva.terminar("canal_desconectado")
                else:
                    espera = min(reserva.vence, reserva.ultimo_contacto + VIGENCIA_CANAL_S) - ahora
                    await asyncio.wait((enlace_perdido, cierre), timeout=min(1, espera), return_when=asyncio.FIRST_COMPLETED)
        finally:
            for tarea in (enlace_perdido, cierre):
                tarea.cancel()
            await asyncio.gather(enlace_perdido, cierre, return_exceptions=True)
            try:
                reserva.confirmo_detener = await self.detener(reserva)
                await asyncio.to_thread(self._repo.cerrar, reserva, reserva.confirmo_detener)
                reserva.cerro_reserva = True
            except Exception:
                logger.exception("No se cerró la reserva de exhibición %s", reserva.id)
            finally:
                self._reservas.pop(reserva.huella, None)
                self._por_unidad.pop(reserva.unidad, None)
                reserva.finalizada.set()

    async def detener(self, reserva):
        async with reserva.mando:
            actual = reserva.movimiento
            if actual is not None and not actual.done():
                actual.cancel()
                await asyncio.gather(actual, return_exceptions=True)
            try:
                await reserva.enlace.ordenar(CODIGO_DETENER, 0)
                return True
            except SinConfirmacion:
                reserva.terminar("detener_sin_confirmar")
                await reserva.enlace.cerrar(1011, "Sin confirmación de DETENER")
                return False

    def mover(self, reserva, codigo, publicar, *, mantenido=False):
        ahora = monotonic()
        if reserva.cerrar.is_set() or ahora + DEMO_MIN_PASO_MS / 1000 >= reserva.vence:
            raise ReglaNegocioError("La prueba está por finalizar")
        if codigo not in reserva.mandos or codigo == CODIGO_DETENER:
            raise ReglaNegocioError("Comando fuera de los permisos de exhibición")
        if mantenido and not reserva.enlace.continuo:
            raise ReglaNegocioError("El firmware de esta unidad no admite el joystick mantenido")
        if (not mantenido and ahora < reserva.proximo_pulso) or (reserva.movimiento is not None and not reserva.movimiento.done()):
            raise ReglaNegocioError("Espera a que termine el pulso anterior")
        espera = max(0, reserva.proximo_pulso - ahora)
        reserva.movimiento = asyncio.create_task(self._movimiento(reserva, codigo, publicar, mantenido, espera))

    async def _movimiento(self, reserva, codigo, publicar, mantenido, espera):
        try:
            if espera:
                await asyncio.sleep(espera)
            vigente, permitido = await asyncio.to_thread(self._repo.vigente, reserva, codigo)
            if not vigente:
                reserva.terminar("permiso_perdido")
                return
            if not permitido:
                await publicar("rechazada", mensaje="El comando ya no está permitido")
                return
            if reserva.cerrar.is_set() or not reserva.enlace.habilitado:
                return
            restante_ms = int((reserva.vence - monotonic()) * 1000)
            duracion_ms = min(MOVIMIENTO_EXHIBICION_MS, restante_ms)
            if duracion_ms < DEMO_MIN_PASO_MS:
                await publicar("rechazada", mensaje="La prueba está por finalizar")
                return
            reserva.proximo_pulso = monotonic() + INTERVALO_MANDOS_S
            if mantenido:
                await reserva.enlace.ordenar(codigo, 0, continuo=True)
                await publicar("movimiento_aplicado", codigo=codigo)
                while not reserva.cerrar.is_set():
                    await asyncio.sleep(1)
                    vigente, permitido = await asyncio.to_thread(self._repo.vigente, reserva, codigo)
                    if not vigente or not permitido:
                        reserva.terminar("permiso_perdido")
                        break
                return
            await reserva.enlace.ordenar(codigo, duracion_ms, demo=True)
            await asyncio.sleep(duracion_ms / 1000)
            await reserva.enlace.ordenar(CODIGO_DETENER, 0)
            await publicar("pulso_confirmado", codigo=codigo)
        except SinConfirmacion:
            reserva.terminar("orden_sin_confirmar")
        except (pymysql.MySQLError, RuntimeError, TimeoutError, OSError):
            reserva.terminar("conexion_interrumpida")

    async def cerrar_todas(self):
        reservas = tuple(self._reservas.values())
        for reserva in reservas:
            reserva.terminar("servidor_detenido")
        await asyncio.gather(*(r.finalizada.wait() for r in reservas))


exhibir = ExhibicionService()
