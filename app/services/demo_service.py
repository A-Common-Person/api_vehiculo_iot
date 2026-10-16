import asyncio
import logging

from app.database import Database, db
from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.repositories.demo_repository import DemoRepository
from app.repositories.estado_repository import EstadoRepository
from app.repositories.vehiculo_repository import VehiculoRepository
from app.websocket.manager import crear_evento, manager

logger = logging.getLogger(__name__)


class DemoService:
    def __init__(self, database: Database = db):
        self._db = database
        self._vehiculos = VehiculoRepository(database)
        self._demos = DemoRepository(database)
        self._estado = EstadoRepository(database)
        self._tareas: dict[int, asyncio.Task] = {}

    def _en_ejecucion(self, id_vehiculo: int) -> bool:
        tarea = self._tareas.get(id_vehiculo)
        return tarea is not None and not tarea.done()

    def _validar(self, id_vehiculo: int, id_demo: int):
        vehiculo = self._vehiculos.obtener_por_id(id_vehiculo)
        if vehiculo is None:
            raise RecursoNoEncontradoError("El vehículo no existe")
        if not vehiculo["activo"]:
            raise ReglaNegocioError("El vehículo está inactivo")

        demos = self._demos.obtener_por_vehiculo(id_vehiculo)
        demo = next((d for d in demos if d["id_demo"] == id_demo), None)
        if demo is None:
            raise RecursoNoEncontradoError(
                "La DEMO no existe o no pertenece a este vehículo"
            )
        if not demo["activo"]:
            raise ReglaNegocioError("La DEMO está inactiva")

        movimientos = self._demos.obtener_movimientos(id_demo)
        if not movimientos:
            raise ReglaNegocioError("La DEMO no tiene movimientos")
        return sorted(movimientos, key=lambda m: m["orden"])

    def _actualizar_estado(self, id_vehiculo: int, id_comando: int, conectado: int):
        with self._db.transaction() as conn:
            self._estado.actualizar(conn, id_vehiculo, id_comando, conectado)

    async def iniciar(self, id_vehiculo: int, id_demo: int):
        if self._en_ejecucion(id_vehiculo):
            raise ReglaNegocioError("Ya hay una DEMO en ejecución para este vehículo")

        movimientos = await asyncio.to_thread(self._validar, id_vehiculo, id_demo)

        # Se vuelve a comprobar justo antes de registrar la tarea (sin await
        # de por medio) para que dos solicitudes simultáneas no pasen ambas.
        if self._en_ejecucion(id_vehiculo):
            raise ReglaNegocioError("Ya hay una DEMO en ejecución para este vehículo")

        self._tareas[id_vehiculo] = asyncio.create_task(
            self._ejecutar(id_vehiculo, id_demo, movimientos)
        )
        return {
            "id_vehiculo": id_vehiculo,
            "id_demo": id_demo,
            "total_movimientos": len(movimientos),
            "mensaje": "DEMO iniciada",
        }

    def cancelar(self, id_vehiculo: int):
        if not self._en_ejecucion(id_vehiculo):
            raise RecursoNoEncontradoError(
                "No hay una DEMO en ejecución para este vehículo"
            )
        self._tareas[id_vehiculo].cancel()
        return {"id_vehiculo": id_vehiculo, "mensaje": "Cancelación solicitada"}

    async def _ejecutar(self, id_vehiculo: int, id_demo: int, movimientos: list):
        try:
            estado = await asyncio.to_thread(self._estado.obtener, id_vehiculo)
            conectado = estado["conectado"] if estado else 0

            await manager.difundir(
                id_vehiculo,
                crear_evento(
                    "demo_inicio",
                    id_vehiculo,
                    id_demo=id_demo,
                    total_movimientos=len(movimientos),
                ),
            )
            for m in movimientos:
                await asyncio.to_thread(
                    self._actualizar_estado, id_vehiculo, m["id_comando"], conectado
                )
                await manager.difundir(
                    id_vehiculo,
                    crear_evento(
                        "demo_movimiento",
                        id_vehiculo,
                        comando=m["comando"],
                        codigo=m["codigo"],
                        id_demo=id_demo,
                        orden=m["orden"],
                        duracion_ms=m["duracion_ms"],
                        pausa_ms=m["pausa_ms"],
                    ),
                )
                await asyncio.sleep(m["duracion_ms"] / 1000)
                await asyncio.sleep(m["pausa_ms"] / 1000)

            await manager.difundir(
                id_vehiculo, crear_evento("demo_fin", id_vehiculo, id_demo=id_demo)
            )
        except asyncio.CancelledError:
            await manager.difundir(
                id_vehiculo,
                crear_evento("demo_cancelada", id_vehiculo, id_demo=id_demo),
            )
            raise
        except Exception:
            logger.exception("Error durante la ejecución de la DEMO")
            await manager.difundir(
                id_vehiculo,
                crear_evento(
                    "demo_error",
                    id_vehiculo,
                    id_demo=id_demo,
                    mensaje="La DEMO terminó por un error",
                ),
            )
        finally:
            if self._tareas.get(id_vehiculo) is asyncio.current_task():
                del self._tareas[id_vehiculo]