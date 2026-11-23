from app.database import Database, db
from app.repositories.auditoria_repository import AuditoriaRepository


SESIONES_VIGENTES = """
    SELECT s.id_sesion, u.id_usuario, u.correo, u.nombre, u.rol
    FROM sesiones_usuario s
    JOIN usuarios u ON u.id_usuario = s.id_usuario
    WHERE s.vence_en > UTC_TIMESTAMP(6) AND s.revocada_en IS NULL AND u.activo = TRUE
"""


class SesionRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def obtener_usuario(self, correo):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_usuario, correo, nombre, rol, password_hash, activo
                FROM usuarios WHERE correo = %s
                """,
                (correo,),
            )
            return cur.fetchone()

    def crear_sesion(self, id_usuario, password_hash, token_hash, segundos):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sesiones_usuario (id_usuario, token_hash, creada_en, vence_en)
                SELECT id_usuario, %s, UTC_TIMESTAMP(6),
                       TIMESTAMPADD(SECOND, %s, UTC_TIMESTAMP(6))
                FROM usuarios WHERE id_usuario = %s AND activo = TRUE AND password_hash = %s
                """,
                (token_hash, segundos, id_usuario, password_hash),
            )
            return cur.rowcount == 1

    def obtener_sesion(self, token_hash):
        return self._buscar_sesion(SESIONES_VIGENTES + " AND s.token_hash = %s", token_hash)

    def obtener_sesion_por_id(self, id_sesion):
        return self._buscar_sesion(SESIONES_VIGENTES + " AND s.id_sesion = %s", id_sesion)

    def _buscar_sesion(self, consulta, parametro):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(consulta, (parametro,))
            return cur.fetchone()

    def revocar_sesion(self, id_sesion):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sesiones_usuario SET revocada_en = UTC_TIMESTAMP(6)
                WHERE id_sesion = %s AND revocada_en IS NULL
                """,
                (id_sesion,),
            )

    def crear_usuario(self, correo, nombre, rol, password_hash, *, creado_por=None):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usuarios (correo, nombre, rol, password_hash) VALUES (%s, %s, %s, %s)",
                (correo, nombre, rol, password_hash),
            )
            id_usuario = cur.lastrowid
            accion = "cliente.creado" if creado_por is not None else "cuenta.creada"
            campo = "id_cliente" if creado_por is not None else "id_usuario_creado"
            AuditoriaRepository.registrar(cur, creado_por, accion, {campo: id_usuario, "nombre": nombre, "rol": rol})
            return id_usuario

    def listar_clientes(self, limite, desplazamiento):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id_usuario, correo, nombre, rol, activo FROM usuarios
                WHERE rol = 'usuario'
                ORDER BY id_usuario LIMIT %s OFFSET %s
                """,
                (limite, desplazamiento),
            )
            return cur.fetchall()
