from app.database import Database, db


class HistorialRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def obtener(self, id_vehiculo: int):
        return self._db.call_procedure("sp_obtener_historial", (id_vehiculo,))

    def registrar(self, conn, id_vehiculo: int, id_comando: int, origen: str):
        return self._db.call_in(
            conn, "sp_registrar_historial", (id_vehiculo, id_comando, origen)
        )
        