import json

from app.database import Database, db


class AuditoriaRepository:
    def __init__(self, database: Database = db):
        self._db = database

    @staticmethod
    def registrar(cur, actor, accion, detalle, id_vehiculo=None, id_reserva=None):
        cur.execute(
            """
            INSERT INTO auditoria_administracion (id_usuario, id_vehiculo, accion, detalle, id_reserva)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (actor, id_vehiculo, accion, json.dumps(detalle), id_reserva),
        )

    def listar(self, id_vehiculo, limite, desplazamiento):
        consulta = """
            SELECT id_evento, id_usuario, id_vehiculo, id_reserva, accion, detalle, ocurrio_en
            FROM auditoria_administracion
        """
        filtros = ()
        if id_vehiculo is not None:
            consulta += " WHERE id_vehiculo = %s"
            filtros = (id_vehiculo,)
        consulta += " ORDER BY ocurrio_en DESC, id_evento DESC LIMIT %s OFFSET %s"

        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(consulta, (*filtros, limite, desplazamiento))
            filas = cur.fetchall()
        for fila in filas:
            if fila["detalle"] is not None:
                fila["detalle"] = json.loads(fila["detalle"])
        return filas
