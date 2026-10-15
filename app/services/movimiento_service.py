from app.database import Database, db
from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.repositories.comando_repository import ComandoRepository
from app.repositories.estado_repository import EstadoRepository
from app.repositories.historial_repository import HistorialRepository
from app.repositories.vehiculo_repository import VehiculoRepository


class MovimientoService:
    def __init__(self, database: Database = db):
        self._db = database
        self._vehiculos = VehiculoRepository(database)
        self._comandos = ComandoRepository(database)
        self._estado = EstadoRepository(database)
        self._historial = HistorialRepository(database)

    def ejecutar(self, id_vehiculo: int, id_comando: int, origen: str = "API"):
        vehiculo = self._vehiculos.obtener_por_id(id_vehiculo)
        if vehiculo is None:
            raise RecursoNoEncontradoError("El vehículo no existe")
        if not vehiculo["activo"]:
            raise ReglaNegocioError("El vehículo está inactivo")

        catalogo = self._comandos.obtener_por_vehiculo(id_vehiculo)
        comando = next((c for c in catalogo if c["id_comando"] == id_comando), None)
        if comando is None:
            raise RecursoNoEncontradoError(
                "El comando no existe o no pertenece a este vehículo"
            )
        if not comando["activo"]:
            raise ReglaNegocioError("El comando está inactivo")

        estado_actual = self._estado.obtener(id_vehiculo)
        conectado = estado_actual["conectado"] if estado_actual else 0

        with self._db.transaction() as conn:
            self._estado.actualizar(conn, id_vehiculo, id_comando, conectado)
            self._historial.registrar(conn, id_vehiculo, id_comando, origen)

        return {
            "id_vehiculo": id_vehiculo,
            "id_comando": id_comando,
            "comando": comando["nombre"],
            "codigo": comando["codigo"],
            "origen": origen,
            "conectado": bool(conectado),
        }