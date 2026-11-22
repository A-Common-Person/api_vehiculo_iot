from app.database import Database, db


CODIGO_AVANZAR = 1
CODIGO_DETENER = 9
# Mandos compatibles con un pulso acotado. La DEMO integrada tiene ejecución propia.
CODIGOS_CONTROL = frozenset({CODIGO_AVANZAR, 2, 3, 4, 5, 6, CODIGO_DETENER, 10, 11, 12, 13, 15})
COMANDOS_HABILITADOS = f"""
    SELECT c.* FROM comandos c
    JOIN inventario_unidades i ON i.id_vehiculo = c.id_vehiculo
    JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
    LEFT JOIN modelos_vehiculo m ON m.id_modelo = i.id_modelo
    LEFT JOIN capacidades_modelo p ON p.id_modelo = i.id_modelo AND p.codigo = c.codigo
    WHERE c.id_vehiculo = %s AND c.activo = TRUE AND v.activo = TRUE AND i.estado_comercial <> 'inactivo'
      AND (c.codigo = {CODIGO_DETENER} OR (m.activo = TRUE AND p.codigo IS NOT NULL))
"""


class ComandoRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def obtener_por_vehiculo(self, id_vehiculo: int):
        return self._db.call_procedure(
            "sp_obtener_comandos_vehiculo", (id_vehiculo,)
        )

    def obtener_habilitados(self, id_vehiculo: int):
        with self._db.lectura() as conn, conn.cursor() as cur:
            cur.execute(COMANDOS_HABILITADOS + " ORDER BY c.codigo, c.id_comando", (id_vehiculo,))
            return cur.fetchall()

    def catalogo_codigos(self):
        with self._db.lectura() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, MIN(nombre) AS nombre FROM comandos GROUP BY codigo ORDER BY codigo")
            return cur.fetchall()

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
