from app.database import Database, db


class ComandoRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def obtener_por_vehiculo(self, id_vehiculo: int):
        return self._db.call_procedure(
            "sp_obtener_comandos_vehiculo", (id_vehiculo,)
        )