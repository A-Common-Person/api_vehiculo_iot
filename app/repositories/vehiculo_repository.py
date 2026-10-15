from app.database import Database, db


class VehiculoRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def obtener_todos(self):
        return self._db.call_procedure("sp_obtener_vehiculos")

    def obtener_por_id(self, id_vehiculo: int):
        rows = self._db.call_procedure("sp_obtener_vehiculo", (id_vehiculo,))
        return rows[0] if rows else None