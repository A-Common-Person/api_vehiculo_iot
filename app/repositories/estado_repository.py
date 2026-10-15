from app.database import Database, db


class EstadoRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def obtener(self, id_vehiculo: int):
        rows = self._db.call_procedure("sp_obtener_estado", (id_vehiculo,))
        return rows[0] if rows else None

    def actualizar(self, conn, id_vehiculo: int, id_comando: int, conectado: int):
        return self._db.call_in(
            conn, "sp_actualizar_estado", (id_vehiculo, id_comando, conectado)
        )