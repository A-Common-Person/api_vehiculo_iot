from app.database import Database, db
from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.repositories.comando_repository import CODIGO_DETENER, CODIGOS_CONTROL, COMANDOS_HABILITADOS
from app.repositories.estado_repository import EstadoRepository
from app.repositories.historial_repository import HistorialRepository
from app.schemas.demo import DEMO_MAX_PASOS, DEMO_MAX_PASO_MS, DEMO_MAX_TOTAL_MS, DEMO_MIN_PASO_MS


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
CODIGOS_MANTENIDOS = frozenset({1, 2, 3, 4, 5, 6, 10, 11})


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

    def abrir(self, unidad, sesion, huella, listo_en, *, codigo, mantenido=False):
        reserva, comandos, _ = self._abrir(unidad, sesion, huella, listo_en, codigo, mantenido)
        return reserva, comandos

    def abrir_demo(self, unidad, sesion, huella, listo_en, id_demo, codigos_dispositivo):
        return self._abrir(unidad, sesion, huella, listo_en, CODIGO_DETENER, False,
                           id_demo=id_demo, codigos_dispositivo=codigos_dispositivo)

    def _abrir(self, unidad, sesion, huella, listo_en, codigo, mantenido, *,
               id_demo=None, codigos_dispositivo=()):
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

            codigos = (codigo, CODIGO_DETENER)
            if id_demo is not None:
                codigos = tuple(sorted(CODIGOS_CONTROL & codigos_dispositivo))
            elif mantenido:
                codigos = (*CODIGOS_MANTENIDOS, CODIGO_DETENER)
            cur.execute(
                COMANDOS_HABILITADOS + " AND c.codigo IN %s ORDER BY c.id_comando FOR SHARE",
                (unidad, codigos),
            )
            habilitados = cur.fetchall()
            comandos = {fila["codigo"]: fila for fila in habilitados}
            if CODIGO_DETENER not in comandos:
                raise ReglaNegocioError("La unidad necesita un comando DETENER activo")
            if codigo not in comandos:
                raise ReglaNegocioError("El comando no está habilitado para esta unidad")
            pasos = self._pasos_demo(cur, unidad, sesion, id_demo, habilitados) if id_demo is not None else None
            cur.execute(
                """
                INSERT INTO reservas_control (id_vehiculo, id_sesion_usuario, vence_en)
                VALUES (%s, %s, UTC_TIMESTAMP(6) + INTERVAL 15 SECOND)
                """,
                (unidad, sesion),
            )
            return cur.lastrowid, comandos, pasos

    @staticmethod
    def _pasos_demo(cur, unidad, sesion, id_demo, habilitados):
        cur.execute(
            """
            SELECT d.activo FROM demos d
            LEFT JOIN propiedad_demo p ON p.id_demo = d.id_demo
            JOIN sesiones_usuario s ON s.id_sesion = %s
            WHERE d.id_vehiculo = %s AND d.id_demo = %s
              AND (p.id_usuario IS NULL OR p.id_usuario = s.id_usuario)
            FOR SHARE
            """,
            (sesion, unidad, id_demo),
        )
        demo = cur.fetchone()
        if demo is None:
            raise RecursoNoEncontradoError("La demo no está disponible para esta unidad")
        if not demo["activo"]:
            raise ReglaNegocioError("La demo está inactiva")
        cur.execute(
            """
            SELECT id_comando, duracion_ms, pausa_ms FROM demo_movimientos
            WHERE id_demo = %s ORDER BY orden LIMIT %s FOR SHARE
            """,
            (id_demo, DEMO_MAX_PASOS + 1),
        )
        pasos = cur.fetchall()
        if not 1 <= len(pasos) <= DEMO_MAX_PASOS:
            raise ReglaNegocioError("La demo debe tener entre 1 y 20 pasos. Ajústala en el editor")
        por_id = {fila["id_comando"]: fila for fila in habilitados}
        for orden, paso in enumerate(pasos, start=1):
            comando = por_id.get(paso["id_comando"])
            if comando is None:
                raise ReglaNegocioError(f"Paso {orden}: el comando no está habilitado en la unidad o en su firmware")
            if not (DEMO_MIN_PASO_MS <= paso["duracion_ms"] <= DEMO_MAX_PASO_MS
                    and 0 <= paso["pausa_ms"] <= DEMO_MAX_PASO_MS):
                raise ReglaNegocioError(f"Paso {orden}: ajusta la duración o la pausa en el editor")
            paso.update(orden=orden, codigo=comando["codigo"], nombre=comando["nombre"])
        if sum(p["duracion_ms"] + p["pausa_ms"] for p in pasos) > DEMO_MAX_TOTAL_MS:
            raise ReglaNegocioError("La demo debe durar 30 segundos o menos")
        return pasos

    def estado_demo(self, unidad, id_comando):
        with self._db.transaction() as conn:
            self._estado.actualizar(conn, unidad, id_comando, 1)

    def renovar_reserva(self, unidad, sesion, huella, reserva):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE reservas_control r JOIN ({PROPIEDAD_ACTIVA}) AS permiso ON TRUE
                JOIN credenciales_dispositivo d ON d.id_vehiculo = r.id_vehiculo
                SET r.vence_en = UTC_TIMESTAMP(6) + INTERVAL 15 SECOND
                WHERE r.id_reserva = %s AND r.id_vehiculo = %s AND r.id_sesion_usuario = %s
                  AND r.finaliza_en IS NULL AND r.vence_en > UTC_TIMESTAMP(6)
                  AND d.token_hash = %s AND d.revocada_en IS NULL
                """,
                (unidad, sesion, reserva, unidad, sesion, huella),
            )
            return cur.rowcount == 1

    def registrar(self, unidad, comandos):
        with self._db.transaction() as conn:
            self._registrar(conn, unidad, comandos)

    def finalizar(self, unidad, reserva, comandos):
        with self._db.transaction() as conn:
            self._registrar(conn, unidad, comandos)
            with conn.cursor() as cur:
                self._cerrar(cur, reserva)

    def _registrar(self, conn, unidad, comandos):
        for comando in comandos:
            self._estado.actualizar(conn, unidad, comando["id_comando"], 1)
            self._historial.registrar(conn, unidad, comando["id_comando"], "CONTROL_4_3")

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
