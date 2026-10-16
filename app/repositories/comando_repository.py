from app.database import Database, db


class ComandoRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def obtener_por_vehiculo(self, id_vehiculo: int):
        return self._db.call_procedure(
            "sp_obtener_comandos_vehiculo", (id_vehiculo,)
        )

    def crear(self, id_vehiculo, nombre, codigo, descripcion):
        return self._db.call_procedure(
            "sp_crear_comando", (id_vehiculo, nombre, codigo, descripcion)
        )

    def actualizar(self, id_comando, nombre, codigo, descripcion, activo):
        return self._db.call_procedure(
            "sp_actualizar_comando",
            (id_comando, nombre, codigo, descripcion, activo),
        )

    def eliminar(self, id_comando):
        return self._db.call_procedure("sp_eliminar_comando", (id_comando,))