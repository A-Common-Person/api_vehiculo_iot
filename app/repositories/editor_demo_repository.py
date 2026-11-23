from app.database import db
from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.comando_repository import CODIGOS_CONTROL, COMANDOS_HABILITADOS
from app.repositories.control_repository import PROPIEDAD_ACTIVA


DEMOS_DEL_EDITOR = """
    SELECT d.id_demo, d.id_vehiculo, d.nombre, d.descripcion, d.activo
    FROM demos d LEFT JOIN propiedad_demo p ON p.id_demo = d.id_demo
    WHERE d.id_vehiculo = %s AND p.id_usuario <=> %s
      AND NOT EXISTS (SELECT 1 FROM movimientos_personalizados m WHERE m.id_demo_origen = d.id_demo)
"""
PASOS_DEMO = """
    SELECT id_comando, duracion_ms, pausa_ms, nombre_movimiento
    FROM demo_movimientos WHERE id_demo = %s ORDER BY orden
"""


class EdicionDemoNoAutorizada(Exception):
    pass


class EditorDemoRepository:
    @staticmethod
    def _autorizar(cur, unidad, sesion):
        if sesion.usuario.rol == "administrador":
            cur.execute(
                """
                SELECT i.id_modelo FROM inventario_unidades i
                JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
                JOIN sesiones_usuario s ON s.id_sesion = %s
                JOIN usuarios u ON u.id_usuario = s.id_usuario
                WHERE i.id_vehiculo = %s AND v.activo = TRUE AND i.estado_comercial <> 'inactivo'
                  AND u.rol = 'administrador' AND u.activo = TRUE
                  AND s.revocada_en IS NULL AND s.vence_en > UTC_TIMESTAMP(6)
                FOR SHARE
                """,
                (sesion.id_sesion, unidad),
            )
            propietario = None
        else:
            cur.execute(PROPIEDAD_ACTIVA + " FOR SHARE", (unidad, sesion.id_sesion))
            propietario = sesion.usuario.id_usuario
        if cur.fetchone() is None:
            raise EdicionDemoNoAutorizada()
        return propietario

    @staticmethod
    def _comandos(cur, unidad):
        cur.execute(
            COMANDOS_HABILITADOS + " AND c.codigo IN %s ORDER BY c.codigo, c.id_comando FOR SHARE",
            (unidad, tuple(sorted(CODIGOS_CONTROL))),
        )
        return cur.fetchall()

    @staticmethod
    def _demo(cur, unidad, propietario, id_demo, *, bloquear=False):
        consulta = DEMOS_DEL_EDITOR + " AND d.id_demo = %s"
        cur.execute(consulta + (" FOR UPDATE" if bloquear else ""), (unidad, propietario, id_demo))
        demo = cur.fetchone()
        if demo is None:
            raise RecursoNoEncontradoError("La demo no está disponible en este editor")
        cur.execute(PASOS_DEMO, (id_demo,))
        return {**demo, "pasos": cur.fetchall()}

    def contexto(self, unidad, sesion):
        with db.transaction() as conn, conn.cursor() as cur:
            propietario = self._autorizar(cur, unidad, sesion)
            cur.execute(DEMOS_DEL_EDITOR + " ORDER BY d.nombre, d.id_demo", (unidad, propietario))
            demos = cur.fetchall()
            cur.execute("""
                SELECT id_movimiento, nombre, id_comando, duracion_ms, pausa_ms FROM movimientos_personalizados
                WHERE id_vehiculo = %s AND id_usuario <=> %s AND eliminado = FALSE ORDER BY nombre, id_movimiento
            """, (unidad, propietario))
            return {"demos": demos, "movimientos": cur.fetchall(), "comandos": self._comandos(cur, unidad)}

    def editar_movimiento(self, unidad, sesion, datos, id_movimiento=None):
        with db.transaction() as conn, conn.cursor() as cur:
            propietario = self._autorizar(cur, unidad, sesion)
            if id_movimiento is not None:
                cur.execute("""
                    SELECT id_movimiento FROM movimientos_personalizados WHERE id_movimiento = %s
                    AND id_vehiculo = %s AND id_usuario <=> %s AND eliminado = FALSE FOR UPDATE
                """, (id_movimiento, unidad, propietario))
                if cur.fetchone() is None:
                    raise RecursoNoEncontradoError("El movimiento no está disponible en esta unidad")
            if datos is None:
                cur.execute("UPDATE movimientos_personalizados SET eliminado = TRUE WHERE id_movimiento = %s", (id_movimiento,))
                accion = "movimiento.eliminado"
            else:
                if datos.id_comando not in {c["id_comando"] for c in self._comandos(cur, unidad)}:
                    raise ReglaNegocioError("Elige un movimiento base habilitado para esta unidad")
                valores = (datos.nombre, datos.id_comando, datos.duracion_ms, datos.pausa_ms)
                if id_movimiento is None:
                    cur.execute("""
                        INSERT INTO movimientos_personalizados (id_vehiculo, id_usuario, nombre, id_comando, duracion_ms, pausa_ms)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (unidad, propietario, *valores))
                    id_movimiento = cur.lastrowid
                    accion = "movimiento.creado"
                else:
                    cur.execute("""
                        UPDATE movimientos_personalizados SET nombre=%s, id_comando=%s, duracion_ms=%s, pausa_ms=%s
                        WHERE id_movimiento=%s
                    """, (*valores, id_movimiento))
                    accion = "movimiento.editado"
            AuditoriaRepository.registrar(cur, sesion.usuario.id_usuario, accion, {"id_movimiento": id_movimiento}, unidad)
            if datos is not None:
                return {"id_movimiento": id_movimiento, **datos.model_dump()}

    def obtener(self, unidad, sesion, id_demo):
        with db.transaction() as conn, conn.cursor() as cur:
            propietario = self._autorizar(cur, unidad, sesion)
            return self._demo(cur, unidad, propietario, id_demo)

    def guardar(self, unidad, sesion, datos, id_demo=None):
        with db.transaction() as conn, conn.cursor() as cur:
            propietario = self._autorizar(cur, unidad, sesion)
            if not datos.activo and datos.descripcion == "Movimiento reutilizable. Solo se usa como paso de otra demo.":
                raise ReglaNegocioError("Actualiza la página y usa Movimientos personalizados para guardar el movimiento")
            habilitados = {fila["id_comando"] for fila in self._comandos(cur, unidad)}
            if any(paso.id_comando not in habilitados for paso in datos.pasos):
                raise ReglaNegocioError("Cada paso debe usar un comando habilitado para esta unidad")
            valores = (datos.nombre, datos.descripcion, datos.activo)
            pasos = [paso.model_dump() for paso in datos.pasos]
            if id_demo is None:
                cur.execute(
                    "INSERT INTO demos (id_vehiculo, nombre, descripcion, activo) VALUES (%s, %s, %s, %s)",
                    (unidad, *valores),
                )
                id_demo = cur.lastrowid
                if propietario is not None:
                    cur.execute("INSERT INTO propiedad_demo (id_demo, id_usuario) VALUES (%s, %s)",
                                (id_demo, propietario))
                accion = "demo.creada"
                pasos_anteriores = []
            else:
                anterior = self._demo(cur, unidad, propietario, id_demo, bloquear=True)
                pasos_anteriores = anterior["pasos"]
                if valores == (anterior["nombre"], anterior["descripcion"], anterior["activo"]) and pasos == list(pasos_anteriores):
                    return anterior
                cur.execute("UPDATE demos SET nombre = %s, descripcion = %s, activo = %s WHERE id_demo = %s",
                            (*valores, id_demo))
                accion = "demo.editada"
            if pasos != list(pasos_anteriores):
                if pasos_anteriores:
                    cur.execute("DELETE FROM demo_movimientos WHERE id_demo = %s", (id_demo,))
                cur.executemany(
                    """
                    INSERT INTO demo_movimientos (id_demo, id_comando, orden, duracion_ms, pausa_ms, nombre_movimiento)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    [(id_demo, paso.id_comando, orden, paso.duracion_ms, paso.pausa_ms, paso.nombre_movimiento)
                     for orden, paso in enumerate(datos.pasos, start=1)],
                )
            AuditoriaRepository.registrar(cur, sesion.usuario.id_usuario, accion, {
                "id_demo": id_demo, "tipo": "empresa" if propietario is None else "privada", "pasos": len(pasos),
            }, unidad)
            return {"id_demo": id_demo, "id_vehiculo": unidad, "nombre": datos.nombre,
                    "descripcion": datos.descripcion, "activo": datos.activo, "pasos": pasos}
