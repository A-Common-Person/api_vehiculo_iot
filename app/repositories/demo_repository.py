from app.database import Database, db


class DemoRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def obtener_por_vehiculo(self, id_vehiculo: int):
        return self._db.call_procedure("sp_obtener_demos", (id_vehiculo,))

    def obtener_movimientos(self, id_demo: int):
        return self._db.call_procedure("sp_obtener_movimientos_demo", (id_demo,))

    def crear_demo(self, id_vehiculo, nombre, descripcion):
        return self._db.call_procedure(
            "sp_crear_demo", (id_vehiculo, nombre, descripcion)
        )

    def actualizar_demo(self, id_demo, nombre, descripcion, activo):
        return self._db.call_procedure(
            "sp_actualizar_demo", (id_demo, nombre, descripcion, activo)
        )

    def eliminar_demo(self, id_demo):
        return self._db.call_procedure("sp_eliminar_demo", (id_demo,))

    def agregar_movimiento(self, id_demo, id_comando, orden, duracion_ms, pausa_ms):
        return self._db.call_procedure(
            "sp_agregar_movimiento_demo",
            (id_demo, id_comando, orden, duracion_ms, pausa_ms),
        )

    def actualizar_movimiento(
        self, id_demo_movimiento, id_comando, orden, duracion_ms, pausa_ms
    ):
        return self._db.call_procedure(
            "sp_actualizar_movimiento_demo",
            (id_demo_movimiento, id_comando, orden, duracion_ms, pausa_ms),
        )

    def eliminar_movimiento(self, id_demo_movimiento):
        return self._db.call_procedure(
            "sp_eliminar_movimiento_demo", (id_demo_movimiento,)
        )