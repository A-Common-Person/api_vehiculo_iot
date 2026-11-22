from app.database import Database, db
from app.exceptions import ReglaNegocioError
from app.repositories.comando_repository import CODIGO_DETENER, CODIGOS_CONTROL, COMANDOS_HABILITADOS
from app.repositories.estado_repository import EstadoRepository
from app.repositories.historial_repository import HistorialRepository


PROPIEDAD_ACTIVA = """
    SELECT i.id_modelo
    FROM inventario_unidades i
    JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
    JOIN asignaciones_vehiculo a ON a.id_vehiculo_vigente = i.id_vehiculo
    JOIN sesiones_usuario s ON s.id_usuario = a.id_usuario
    JOIN usuarios u ON u.id_usuario = s.id_usuario
    WHERE i.id_vehiculo = %s AND s.id_sesion = %s
      AND v.activo = TRUE AND i.estado_comercial = 'asignado'
      AND a.inicia_en <= UTC_TIMESTAMP(6) AND u.rol = 'usuario' AND u.activo = TRUE
      AND s.revocada_en IS NULL AND s.vence_en > UTC_TIMESTAMP(6)
"""


class ControlNoAutorizado(Exception):
    pass


class ControlRepository:
    def __init__(self, database: Database = db):
        self._db = database
        self._estado = EstadoRepository(database)
        self._historial = HistorialRepository(database)

    def puede_operar(self, unidad, sesion):
        with self._db.lectura() as conn, conn.cursor() as cur:
            cur.execute(PROPIEDAD_ACTIVA, (unidad, sesion))
            return cur.fetchone() is not None

    def estado_control(self, unidad, sesion, huella):
        with self._db.lectura() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT EXISTS (
                    SELECT 1 FROM credenciales_dispositivo
                    WHERE id_vehiculo = %s AND token_hash = %s AND revocada_en IS NULL
                ) AS credencial_vigente, habilitados.codigo
                FROM ({PROPIEDAD_ACTIVA}) AS permiso
                LEFT JOIN ({COMANDOS_HABILITADOS} AND c.codigo IN %s) AS habilitados ON TRUE
                """,
                (unidad, huella, unidad, sesion, unidad, tuple(CODIGOS_CONTROL)),
            )
            filas = cur.fetchall()
            if not filas:
                raise ControlNoAutorizado()
            codigos = {fila["codigo"] for fila in filas if fila["codigo"] is not None}
            return bool(filas[0]["credencial_vigente"]), codigos

    def credencial_vigente(self, unidad, huella):
        with self._db.lectura() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM credenciales_dispositivo d
                JOIN inventario_unidades i ON i.id_vehiculo = d.id_vehiculo
                JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
                WHERE d.id_vehiculo = %s AND d.token_hash = %s AND d.revocada_en IS NULL
                  AND v.activo = TRUE AND i.estado_comercial <> 'inactivo'
                """,
                (unidad, huella),
            )
            return cur.fetchone() is not None

    def abrir(self, unidad, sesion, huella, listo_en, *, codigo):
        with self._db.transaction() as conn, conn.cursor() as cur:
            # Bloquea primero el modelo, igual que las ediciones de inventario y capacidades.
            cur.execute(
                """
                SELECT id_modelo FROM modelos_vehiculo
                WHERE id_modelo = (SELECT id_modelo FROM inventario_unidades WHERE id_vehiculo = %s)
                FOR SHARE
                """,
                (unidad,),
            )
            modelo = cur.fetchone()
            cur.execute(PROPIEDAD_ACTIVA + " FOR UPDATE", (unidad, sesion))
            permiso = cur.fetchone()
            if permiso is None:
                raise ControlNoAutorizado()
            if modelo is None or modelo["id_modelo"] != permiso["id_modelo"]:
                raise ReglaNegocioError("El modelo de la unidad cambió. Vuelve a consultar la unidad")

            cur.execute(
                "SELECT 1 FROM credenciales_dispositivo WHERE id_vehiculo = %s AND token_hash = %s "
                "AND revocada_en IS NULL FOR UPDATE",
                (unidad, huella),
            )
            if cur.fetchone() is None:
                raise ReglaNegocioError("La credencial del dispositivo dejó de estar vigente")

            cur.execute(
                """
                SELECT id_reserva, vence_en, vence_en <= UTC_TIMESTAMP(6) AS vencida
                FROM reservas_control WHERE id_vehiculo_reservado = %s FOR UPDATE
                """,
                (unidad,),
            )
            abierta = cur.fetchone()
            if abierta is not None:
                if not abierta["vencida"] or listo_en < abierta["vence_en"]:
                    raise ReglaNegocioError("El vehículo tiene una reserva pendiente")
                # Un enlace nuevo confirma que el dispositivo volvió a arrancar detenido.
                self._cerrar(cur, abierta["id_reserva"])

            cur.execute(
                COMANDOS_HABILITADOS + " AND c.codigo IN (%s, %s) ORDER BY c.id_comando FOR SHARE",
                (unidad, codigo, CODIGO_DETENER),
            )
            comandos = {fila["codigo"]: fila for fila in cur.fetchall()}
            if CODIGO_DETENER not in comandos:
                raise ReglaNegocioError("La unidad necesita un comando DETENER activo")
            if codigo not in comandos:
                raise ReglaNegocioError("El comando no está habilitado para esta unidad")
            cur.execute(
                """
                INSERT INTO reservas_control (id_vehiculo, id_sesion_usuario, vence_en)
                VALUES (%s, %s, UTC_TIMESTAMP(6) + INTERVAL 15 SECOND)
                """,
                (unidad, sesion),
            )
            return cur.lastrowid, comandos

    def finalizar(self, unidad, reserva, comandos):
        with self._db.transaction() as conn:
            for comando in comandos:
                self._estado.actualizar(conn, unidad, comando["id_comando"], 1)
                self._historial.registrar(conn, unidad, comando["id_comando"], "CONTROL_4_3")
            with conn.cursor() as cur:
                self._cerrar(cur, reserva)

    @staticmethod
    def _cerrar(cur, reserva):
        cur.execute(
            "UPDATE reservas_control SET finaliza_en = UTC_TIMESTAMP(6) WHERE id_reserva = %s AND finaliza_en IS NULL",
            (reserva,),
        )

    def emitir_credencial(self, unidad, huella):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO credenciales_dispositivo (id_vehiculo, token_hash)
                SELECT i.id_vehiculo, %s FROM inventario_unidades i
                JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
                WHERE i.id_vehiculo = %s AND i.estado_comercial <> 'inactivo' AND v.activo = TRUE
                ON DUPLICATE KEY UPDATE token_hash = %s, emitida_en = UTC_TIMESTAMP(6), revocada_en = NULL
                """,
                (huella, unidad, huella),
            )
            if cur.rowcount == 0:
                raise ReglaNegocioError("La unidad no está disponible para registrar un dispositivo")
