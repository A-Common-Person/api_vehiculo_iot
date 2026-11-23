from app.database import db
from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.comando_repository import CODIGO_DETENER, COMANDOS_HABILITADOS
from app.repositories.control_repository import ControlRepository
from app.repositories.estado_repository import EstadoRepository
from app.schemas.exhibicion import CODIGOS_EXHIBICION


UNIDAD_PUBLICA = """
    FROM inventario_unidades i
    JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
    JOIN modelos_vehiculo m ON m.id_modelo = i.id_modelo
    WHERE i.estado_comercial = 'exhibicion' AND v.activo = TRUE AND m.activo = TRUE
      AND NOT EXISTS (SELECT 1 FROM asignaciones_vehiculo a WHERE a.id_vehiculo_vigente = i.id_vehiculo)
"""


class ExhibicionRepository:
    def catalogo(self):
        with db.lectura() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_modelo, nombre, descripcion FROM modelos_vehiculo WHERE activo = TRUE ORDER BY nombre")
            modelos = {fila["id_modelo"]: {**fila, "capacidades": [], "unidades": []} for fila in cur.fetchall()}
            cur.execute("""
                SELECT m.id_modelo, p.codigo FROM capacidades_modelo p
                JOIN modelos_vehiculo m ON m.id_modelo = p.id_modelo AND m.activo = TRUE
                WHERE p.permite_invitado = TRUE AND p.codigo IN %s ORDER BY p.codigo
            """, (tuple(CODIGOS_EXHIBICION),))
            for fila in cur.fetchall():
                modelo = modelos.get(fila["id_modelo"])
                if modelo is not None:
                    modelo["capacidades"].append(CODIGOS_EXHIBICION[fila["codigo"]])
            cur.execute(f"""
                SELECT i.id_modelo, i.id_vehiculo,
                    (SELECT r.vence_en FROM reservas_control r WHERE r.id_vehiculo_reservado = i.id_vehiculo) AS vence_en,
                    (SELECT GROUP_CONCAT(DISTINCT c.codigo) FROM comandos c
                     LEFT JOIN capacidades_modelo p ON p.id_modelo = i.id_modelo AND p.codigo = c.codigo
                     WHERE c.id_vehiculo = i.id_vehiculo AND c.activo = TRUE AND c.codigo IN %s
                       AND (c.codigo = %s OR p.permite_invitado = TRUE)) AS codigos
                {UNIDAD_PUBLICA} ORDER BY i.id_vehiculo
            """, (tuple(CODIGOS_EXHIBICION), CODIGO_DETENER))
            for unidad in cur.fetchall():
                modelo = modelos.get(unidad.pop("id_modelo"))
                unidad["codigos"] = {int(c) for c in (unidad["codigos"] or "").split(",") if c}
                if modelo is not None:
                    modelo["unidades"].append(unidad)
            return list(modelos.values())

    def publica(self, unidad):
        with db.lectura() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT 1 {UNIDAD_PUBLICA} AND i.id_vehiculo = %s", (unidad,))
            return cur.fetchone() is not None

    def abrir(self, unidad, invitado, enlace, segundos):
        with db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id_modelo FROM modelos_vehiculo WHERE id_modelo = "
                "(SELECT id_modelo FROM inventario_unidades WHERE id_vehiculo = %s) FOR SHARE",
                (unidad,),
            )
            modelo = cur.fetchone()
            cur.execute(f"SELECT i.id_modelo {UNIDAD_PUBLICA} AND i.id_vehiculo = %s FOR UPDATE", (unidad,))
            actual = cur.fetchone()
            if actual is None:
                raise RecursoNoEncontradoError("La unidad no está en exhibición")
            if modelo is None or modelo["id_modelo"] != actual["id_modelo"]:
                raise ReglaNegocioError("El modelo de exhibición cambió. Vuelve a consultar el catálogo")
            cur.execute(
                "SELECT 1 FROM credenciales_dispositivo WHERE id_vehiculo = %s AND token_hash = %s "
                "AND revocada_en IS NULL FOR SHARE", (unidad, enlace.huella),
            )
            if cur.fetchone() is None:
                raise ReglaNegocioError("El dispositivo no está disponible para la prueba")
            cur.execute("""
                SELECT id_reserva, token_invitado_hash, vence_en,
                       vence_en <= UTC_TIMESTAMP(6) AS vencida
                FROM reservas_control WHERE id_vehiculo_reservado = %s FOR UPDATE
            """, (unidad,))
            previa = cur.fetchone()
            if previa is not None:
                if not previa["vencida"] or enlace.listo_en < previa["vence_en"]:
                    raise ReglaNegocioError("La unidad está ocupada")
                if previa["token_invitado_hash"] is None:
                    ControlRepository._cerrar(cur, previa["id_reserva"])
                else:
                    self._cerrar(cur, previa["id_reserva"], unidad, "reserva_vencida", False)
            codigos_hw = tuple(codigo for codigo in CODIGOS_EXHIBICION if codigo in enlace.codigos)
            cur.execute(
                COMANDOS_HABILITADOS + " AND c.codigo IN %s AND (c.codigo = %s OR p.permite_invitado = TRUE) FOR SHARE",
                (unidad, codigos_hw, CODIGO_DETENER),
            )
            mandos = {fila["codigo"]: fila["id_comando"] for fila in cur.fetchall()}
            if CODIGO_DETENER not in mandos or len(mandos) < 2:
                raise ReglaNegocioError("El modelo requiere mandos de exhibición y DETENER activos")
            cur.execute("""
                INSERT INTO reservas_control (id_vehiculo, token_invitado_hash, vence_en)
                VALUES (%s, %s, UTC_TIMESTAMP(6) + INTERVAL %s SECOND)
            """, (unidad, invitado, segundos))
            reserva = cur.lastrowid
            AuditoriaRepository.registrar(cur, None, "invitado.inicio",
                                          {"segundos": segundos, "codigos": sorted(mandos)}, unidad, reserva)
            return reserva, mandos

    def vigente(self, reserva, codigo):
        with db.lectura() as conn, conn.cursor() as cur:
            cur.execute(f"""
                SELECT 1 {UNIDAD_PUBLICA} AND i.id_vehiculo = %s
                  AND EXISTS (SELECT 1 FROM reservas_control r
                    WHERE r.id_reserva = %s AND r.token_invitado_hash = %s AND r.id_vehiculo_reservado = i.id_vehiculo
                      AND r.vence_en > UTC_TIMESTAMP(6))
                  AND EXISTS (SELECT 1 FROM credenciales_dispositivo d
                    WHERE d.id_vehiculo = i.id_vehiculo AND d.token_hash = %s AND d.revocada_en IS NULL)
            """, (reserva.unidad, reserva.id, reserva.huella, reserva.enlace.huella))
            if cur.fetchone() is None:
                return False, False
            cur.execute(COMANDOS_HABILITADOS + " AND c.codigo = %s AND p.permite_invitado = TRUE", (reserva.unidad, codigo))
            return True, cur.fetchone() is not None

    @staticmethod
    def _cerrar(cur, reserva, unidad, motivo, detencion):
        cur.execute("UPDATE reservas_control SET finaliza_en = UTC_TIMESTAMP(6) "
                    "WHERE id_reserva = %s AND finaliza_en IS NULL", (reserva,))
        if cur.rowcount:
            AuditoriaRepository.registrar(cur, None, "invitado.fin", {
                "motivo": motivo, "detencion_confirmada": detencion,
            }, unidad, reserva)

    def cerrar(self, reserva, confirmado):
        with db.transaction() as conn, conn.cursor() as cur:
            if confirmado:
                EstadoRepository().actualizar(conn, reserva.unidad, reserva.mandos[CODIGO_DETENER], 1)
            self._cerrar(cur, reserva.id, reserva.unidad, reserva.motivo, confirmado)
