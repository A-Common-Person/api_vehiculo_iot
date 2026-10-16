from app.database import Database, db
from app.exceptions import RecursoNoEncontradoError
from app.repositories.comando_repository import ComandoRepository
from app.repositories.demo_repository import DemoRepository
from app.repositories.estado_repository import EstadoRepository
from app.repositories.historial_repository import HistorialRepository
from app.repositories.vehiculo_repository import VehiculoRepository


class ConsultaService:
    LIMITE_HISTORIAL = 10

    def __init__(self, database: Database = db):
        self._vehiculos = VehiculoRepository(database)
        self._comandos = ComandoRepository(database)
        self._estado = EstadoRepository(database)
        self._historial = HistorialRepository(database)
        self._demos = DemoRepository(database)

    def _vehiculo(self, id_vehiculo: int):
        vehiculo = self._vehiculos.obtener_por_id(id_vehiculo)
        if vehiculo is None:
            raise RecursoNoEncontradoError("El vehículo no existe")
        return vehiculo

    def listar_vehiculos(self):
        return self._vehiculos.obtener_todos()

    def detalle_vehiculo(self, id_vehiculo: int):
        vehiculo = self._vehiculo(id_vehiculo)
        return {
            **vehiculo,
            "comandos": self._comandos.obtener_por_vehiculo(id_vehiculo),
            "estado": self._estado.obtener(id_vehiculo),
            "demos": self._demos.obtener_por_vehiculo(id_vehiculo),
        }

    def comandos(self, id_vehiculo: int):
        self._vehiculo(id_vehiculo)
        return self._comandos.obtener_por_vehiculo(id_vehiculo)

    def estado(self, id_vehiculo: int):
        self._vehiculo(id_vehiculo)
        return self._estado.obtener(id_vehiculo)

    def historial(self, id_vehiculo: int):
        self._vehiculo(id_vehiculo)
        registros = sorted(
            self._historial.obtener(id_vehiculo),
            key=lambda r: r["id_historial"],
            reverse=True,
        )
        return registros[: self.LIMITE_HISTORIAL]

    def demos(self, id_vehiculo: int):
        self._vehiculo(id_vehiculo)
        return self._demos.obtener_por_vehiculo(id_vehiculo)

    def movimientos_demo(self, id_vehiculo: int, id_demo: int):
        self._vehiculo(id_vehiculo)
        demos = self._demos.obtener_por_vehiculo(id_vehiculo)
        if not any(d["id_demo"] == id_demo for d in demos):
            raise RecursoNoEncontradoError(
                "La DEMO no existe o no pertenece a este vehículo"
            )
        movimientos = self._demos.obtener_movimientos(id_demo)
        return sorted(movimientos, key=lambda m: m["orden"])