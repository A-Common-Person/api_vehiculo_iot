from app.database import Database, db


class DemoRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def obtener_por_vehiculo(self, id_vehiculo: int):
        return self._db.call_procedure("sp_obtener_demos", (id_vehiculo,))

    def obtener_movimientos(self, id_demo: int):
        return self._db.call_procedure("sp_obtener_movimientos_demo", (id_demo,))