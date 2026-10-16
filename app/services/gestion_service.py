from app.database import Database, db
from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.repositories.comando_repository import ComandoRepository
from app.repositories.demo_repository import DemoRepository
from app.repositories.vehiculo_repository import VehiculoRepository


class GestionService:
    def __init__(self, database: Database = db):
        self._vehiculos = VehiculoRepository(database)
        self._comandos = ComandoRepository(database)
        self._demos = DemoRepository(database)

    @staticmethod
    def _respuesta(mensaje, filas):
        return {"mensaje": mensaje, "resultado": list(filas or [])}

    # ---------- validaciones de existencia y pertenencia ----------
    def _vehiculo(self, id_vehiculo):
        if self._vehiculos.obtener_por_id(id_vehiculo) is None:
            raise RecursoNoEncontradoError("El vehículo no existe")

    def _comando(self, id_vehiculo, id_comando):
        self._vehiculo(id_vehiculo)
        catalogo = self._comandos.obtener_por_vehiculo(id_vehiculo)
        comando = next((c for c in catalogo if c["id_comando"] == id_comando), None)
        if comando is None:
            raise RecursoNoEncontradoError(
                "El comando no existe o no pertenece a este vehículo"
            )
        return comando

    def _comando_activo(self, id_vehiculo, id_comando):
        comando = self._comando(id_vehiculo, id_comando)
        if not comando["activo"]:
            raise ReglaNegocioError("El comando está inactivo")

    def _demo(self, id_vehiculo, id_demo):
        self._vehiculo(id_vehiculo)
        demos = self._demos.obtener_por_vehiculo(id_vehiculo)
        if not any(d["id_demo"] == id_demo for d in demos):
            raise RecursoNoEncontradoError(
                "La DEMO no existe o no pertenece a este vehículo"
            )

    def _movimiento(self, id_vehiculo, id_demo, id_movimiento):
        self._demo(id_vehiculo, id_demo)
        movimientos = self._demos.obtener_movimientos(id_demo)
        if not any(m["id_demo_movimiento"] == id_movimiento for m in movimientos):
            raise RecursoNoEncontradoError(
                "El movimiento no existe o no pertenece a esta DEMO"
            )

    # ---------- vehículos ----------
    def crear_vehiculo(self, d):
        filas = self._vehiculos.crear(
            d.nombre, d.modelo, d.descripcion, d.microcontrolador
        )
        return self._respuesta("Vehículo creado", filas)

    def actualizar_vehiculo(self, id_vehiculo, d):
        self._vehiculo(id_vehiculo)
        filas = self._vehiculos.actualizar(
            id_vehiculo,
            d.nombre,
            d.modelo,
            d.descripcion,
            d.microcontrolador,
            int(d.activo),
        )
        return self._respuesta("Vehículo actualizado", filas)

    def eliminar_vehiculo(self, id_vehiculo):
        self._vehiculo(id_vehiculo)
        filas = self._vehiculos.eliminar(id_vehiculo)
        return self._respuesta("Vehículo eliminado", filas)

    # ---------- comandos ----------
    def crear_comando(self, id_vehiculo, d):
        self._vehiculo(id_vehiculo)
        filas = self._comandos.crear(id_vehiculo, d.nombre, d.codigo, d.descripcion)
        return self._respuesta("Comando creado", filas)

    def actualizar_comando(self, id_vehiculo, id_comando, d):
        self._comando(id_vehiculo, id_comando)
        filas = self._comandos.actualizar(
            id_comando, d.nombre, d.codigo, d.descripcion, int(d.activo)
        )
        return self._respuesta("Comando actualizado", filas)

    def eliminar_comando(self, id_vehiculo, id_comando):
        self._comando(id_vehiculo, id_comando)
        filas = self._comandos.eliminar(id_comando)
        return self._respuesta("Comando eliminado", filas)

    # ---------- demos ----------
    def crear_demo(self, id_vehiculo, d):
        self._vehiculo(id_vehiculo)
        filas = self._demos.crear_demo(id_vehiculo, d.nombre, d.descripcion)
        return self._respuesta("DEMO creada", filas)

    def actualizar_demo(self, id_vehiculo, id_demo, d):
        self._demo(id_vehiculo, id_demo)
        filas = self._demos.actualizar_demo(
            id_demo, d.nombre, d.descripcion, int(d.activo)
        )
        return self._respuesta("DEMO actualizada", filas)

    def eliminar_demo(self, id_vehiculo, id_demo):
        self._demo(id_vehiculo, id_demo)
        filas = self._demos.eliminar_demo(id_demo)
        return self._respuesta("DEMO eliminada", filas)

    # ---------- movimientos de demo ----------
    def agregar_movimiento(self, id_vehiculo, id_demo, d):
        self._demo(id_vehiculo, id_demo)
        self._comando_activo(id_vehiculo, d.id_comando)
        filas = self._demos.agregar_movimiento(
            id_demo, d.id_comando, d.orden, d.duracion_ms, d.pausa_ms
        )
        return self._respuesta("Movimiento agregado a la DEMO", filas)

    def actualizar_movimiento(self, id_vehiculo, id_demo, id_movimiento, d):
        self._movimiento(id_vehiculo, id_demo, id_movimiento)
        self._comando_activo(id_vehiculo, d.id_comando)
        filas = self._demos.actualizar_movimiento(
            id_movimiento, d.id_comando, d.orden, d.duracion_ms, d.pausa_ms
        )
        return self._respuesta("Movimiento de DEMO actualizado", filas)

    def eliminar_movimiento(self, id_vehiculo, id_demo, id_movimiento):
        self._movimiento(id_vehiculo, id_demo, id_movimiento)
        filas = self._demos.eliminar_movimiento(id_movimiento)
        return self._respuesta("Movimiento de DEMO eliminado", filas)