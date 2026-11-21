from app.database import Database, db


class InventarioRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def listar(self):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT v.*, i.id_modelo, m.nombre AS modelo_comercial,
                       i.estado_comercial, a.id_asignacion, a.id_usuario AS id_propietario
                FROM inventario_unidades i
                JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
                LEFT JOIN modelos_vehiculo m ON m.id_modelo = i.id_modelo
                LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo_vigente = i.id_vehiculo
                ORDER BY v.id_vehiculo
                """
            )
            return cur.fetchall()

    def listar_asignados(self, id_usuario):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT v.* FROM asignaciones_vehiculo a
                JOIN inventario_unidades i ON i.id_vehiculo = a.id_vehiculo_vigente
                JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
                WHERE a.id_usuario = %s AND i.estado_comercial = 'asignado'
                  AND a.inicia_en <= UTC_TIMESTAMP(6) AND v.activo = TRUE
                ORDER BY v.id_vehiculo
                """,
                (id_usuario,),
            )
            return cur.fetchall()

    def puede_consultar(self, id_vehiculo, usuario):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM inventario_unidades i
                JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
                LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo_vigente = i.id_vehiculo
                WHERE i.id_vehiculo = %s AND i.estado_comercial <> 'inactivo' AND v.activo = TRUE
                  AND (
                      (%s = 'usuario' AND i.estado_comercial = 'asignado'
                       AND a.id_usuario = %s AND a.inicia_en <= UTC_TIMESTAMP(6))
                      OR (%s = 'administrador' AND (
                          (i.estado_comercial IN ('disponible', 'exhibicion') AND a.id_asignacion IS NULL)
                          OR (i.estado_comercial = 'asignado' AND a.inicia_en <= UTC_TIMESTAMP(6) AND EXISTS (
                              SELECT 1 FROM autorizaciones_soporte sa
                              WHERE sa.id_asignacion = a.id_asignacion AND sa.id_administrador = %s
                                AND sa.concedida_en <= UTC_TIMESTAMP(6)
                                AND sa.revocada_en IS NULL AND sa.vence_en > UTC_TIMESTAMP(6)
                          ))
                      ))
                  )
                """,
                (id_vehiculo, usuario.rol, usuario.id_usuario, usuario.rol, usuario.id_usuario),
            )
            return cur.fetchone() is not None

    def demos_privadas_ajenas(self, id_vehiculo, id_usuario):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id_demo FROM propiedad_demo p
                JOIN demos d ON d.id_demo = p.id_demo
                WHERE d.id_vehiculo = %s AND p.id_usuario <> %s
                """,
                (id_vehiculo, id_usuario),
            )
            return {fila["id_demo"] for fila in cur.fetchall()}


inventario = InventarioRepository()
