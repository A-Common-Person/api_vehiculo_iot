from app.database import Database, db
from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.inventario_repository import InventarioRepository


CAMPOS_ASIGNACION = "id_asignacion, id_vehiculo, id_usuario, inicia_en, finaliza_en"


class AsignacionRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def historial(self, id_vehiculo, limite, desplazamiento):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_vehiculo FROM inventario_unidades WHERE id_vehiculo = %s", (id_vehiculo,))
            if cur.fetchone() is None:
                raise RecursoNoEncontradoError("La unidad no existe en el inventario")
            cur.execute(
                f"""
                SELECT {CAMPOS_ASIGNACION} FROM asignaciones_vehiculo
                WHERE id_vehiculo = %s
                ORDER BY inicia_en DESC, id_asignacion DESC LIMIT %s OFFSET %s
                """,
                (id_vehiculo, limite, desplazamiento),
            )
            return cur.fetchall()

    @staticmethod
    def _asignacion_vigente(cur, id_vehiculo, estado):
        cur.execute(
            f"SELECT {CAMPOS_ASIGNACION} FROM asignaciones_vehiculo WHERE id_vehiculo_vigente = %s FOR UPDATE",
            (id_vehiculo,),
        )
        actual = cur.fetchone()
        if (actual is not None) != (estado == "asignado"):
            raise ReglaNegocioError("El estado comercial y la asignación vigente son inconsistentes")
        return actual

    @staticmethod
    def _validar_cliente(cur, id_usuario):
        cur.execute("SELECT activo FROM usuarios WHERE id_usuario = %s AND rol = 'usuario' FOR SHARE", (id_usuario,))
        cliente = cur.fetchone()
        if cliente is None:
            raise RecursoNoEncontradoError("El cliente no existe")
        if not cliente["activo"]:
            raise ReglaNegocioError("El cliente está inactivo")

    @staticmethod
    def _cerrar(cur, id_asignacion):
        cur.execute(
            "UPDATE asignaciones_vehiculo SET finaliza_en = UTC_TIMESTAMP(6) WHERE id_asignacion = %s",
            (id_asignacion,),
        )
        cur.execute(
            """
            UPDATE autorizaciones_soporte SET revocada_en = UTC_TIMESTAMP(6)
            WHERE id_asignacion = %s AND revocada_en IS NULL
            """,
            (id_asignacion,),
        )

    def asignar(self, id_vehiculo, id_usuario, id_asignacion_esperada, actor):
        with self._db.transaction() as conn, conn.cursor() as cur:
            unidad = InventarioRepository.bloquear_unidad(cur, id_vehiculo)
            if not unidad["activo"] or unidad["estado_comercial"] not in ("disponible", "asignado"):
                raise ReglaNegocioError("Sólo puedes asignar unidades disponibles o ya asignadas")
            actual = self._asignacion_vigente(cur, id_vehiculo, unidad["estado_comercial"])
            self._validar_cliente(cur, id_usuario)
            if actual is not None and actual["id_usuario"] == id_usuario:
                return actual

            anterior = actual["id_asignacion"] if actual else None
            if anterior != id_asignacion_esperada:
                raise ReglaNegocioError("La asignación cambió; consulta el inventario y confirma la asignación vigente")
            InventarioRepository.comprobar_reserva(cur, id_vehiculo)
            if anterior is not None:
                self._cerrar(cur, anterior)
            cur.execute(
                "INSERT INTO asignaciones_vehiculo (id_vehiculo, id_usuario) VALUES (%s, %s)",
                (id_vehiculo, id_usuario),
            )
            nueva = cur.lastrowid
            cur.execute(
                "UPDATE inventario_unidades SET estado_comercial = 'asignado' WHERE id_vehiculo = %s",
                (id_vehiculo,),
            )
            AuditoriaRepository.registrar(
                cur, actor, "unidad.reasignada" if anterior is not None else "unidad.asignada",
                {"id_asignacion": nueva, "id_asignacion_anterior": anterior, "id_cliente": id_usuario,
                 "cliente_anterior": actual["id_usuario"] if actual else None},
                id_vehiculo,
            )
            cur.execute(f"SELECT {CAMPOS_ASIGNACION} FROM asignaciones_vehiculo WHERE id_asignacion = %s", (nueva,))
            return cur.fetchone()

    def liberar(self, id_vehiculo, id_asignacion_esperada, actor):
        with self._db.transaction() as conn, conn.cursor() as cur:
            unidad = InventarioRepository.bloquear_unidad(cur, id_vehiculo)
            actual = self._asignacion_vigente(cur, id_vehiculo, unidad["estado_comercial"])
            if actual is None:
                return
            if actual["id_asignacion"] != id_asignacion_esperada:
                raise ReglaNegocioError("La asignación cambió; consulta el inventario antes de liberar")
            InventarioRepository.comprobar_reserva(cur, id_vehiculo)
            self._cerrar(cur, id_asignacion_esperada)
            estado = "disponible" if unidad["activo"] else "inactivo"
            cur.execute("UPDATE inventario_unidades SET estado_comercial = %s WHERE id_vehiculo = %s", (estado, id_vehiculo))
            AuditoriaRepository.registrar(
                cur, actor, "unidad.liberada",
                {"id_asignacion": id_asignacion_esperada, "id_cliente": actual["id_usuario"]},
                id_vehiculo,
            )
