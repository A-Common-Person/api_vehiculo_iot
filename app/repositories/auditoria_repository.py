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
            SELECT ref.actor, ref.unidad, %s, JSON_MERGE_PATCH(%s, JSON_OBJECT(
                       'actor_nombre', u.nombre, 'actor_rol', u.rol, 'unidad_nombre', v.nombre)), %s
            FROM (SELECT %s AS actor, %s AS unidad) ref
            LEFT JOIN usuarios u ON u.id_usuario = ref.actor
            LEFT JOIN vehiculos v ON v.id_vehiculo = ref.unidad
            """,
            (accion, json.dumps(detalle), id_reserva, actor, id_vehiculo),
        )

    @staticmethod
    def cambios(anterior, actual):
        return {campo: {"antes": anterior.get(campo), "despues": valor}
                for campo, valor in actual.items() if anterior.get(campo) != valor}

    def listar(self, id_vehiculo, limite, desplazamiento, antes_de=None, despues_de=None):
        consulta = """
            SELECT a.id_evento, a.id_usuario, a.id_vehiculo, a.id_reserva, a.accion, a.detalle, a.ocurrio_en,
                   u.nombre AS actor_nombre, u.rol AS actor_rol, v.nombre AS unidad_nombre
            FROM auditoria_administracion a
            LEFT JOIN usuarios u ON u.id_usuario = a.id_usuario
            LEFT JOIN vehiculos v ON v.id_vehiculo = a.id_vehiculo
            WHERE a.accion NOT IN ('sesion.iniciada', 'sesion.cerrada')
        """
        filtros = []
        if id_vehiculo is not None:
            consulta += " AND a.id_vehiculo = %s"
            filtros.append(id_vehiculo)
        if antes_de is not None:
            consulta += " AND a.id_evento < %s"
            filtros.append(antes_de)
        if despues_de is not None:
            consulta += " AND a.id_evento > %s ORDER BY a.id_evento ASC"
            filtros.append(despues_de)
        else:
            consulta += " ORDER BY a.id_evento DESC"
        consulta += " LIMIT %s OFFSET %s"

        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute(consulta, (*filtros, limite, desplazamiento))
            filas = cur.fetchall()
        for fila in filas:
            if fila["detalle"] is not None:
                fila["detalle"] = json.loads(fila["detalle"])
                for campo in ("actor_nombre", "actor_rol", "unidad_nombre"):
                    fila[campo] = fila["detalle"].pop(campo, fila[campo])
        return filas
