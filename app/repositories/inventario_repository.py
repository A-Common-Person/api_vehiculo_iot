from pymysql.err import IntegrityError

from app.database import Database, db
from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.comando_repository import CODIGO_DETENER, CODIGOS_CONTROL
from app.schemas.exhibicion import CODIGOS_EXHIBICION


CONSULTA_INVENTARIO = """
    SELECT v.*, i.id_modelo, m.nombre AS modelo_comercial,
           i.estado_comercial, a.id_asignacion, a.id_usuario AS id_propietario
    FROM inventario_unidades i
    JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
    LEFT JOIN modelos_vehiculo m ON m.id_modelo = i.id_modelo
    LEFT JOIN asignaciones_vehiculo a ON a.id_vehiculo_vigente = i.id_vehiculo
"""


class InventarioRepository:
    def __init__(self, database: Database = db):
        self._db = database

    def listar(self):
        with self._db.lectura() as conn, conn.cursor() as cur:
            cur.execute(CONSULTA_INVENTARIO + " ORDER BY v.id_vehiculo")
            return cur.fetchall()

    def listar_modelos(self):
        with self._db.lectura() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.id_modelo, m.nombre, m.descripcion, m.activo, p.codigo, p.permite_invitado
                FROM modelos_vehiculo m
                LEFT JOIN capacidades_modelo p ON p.id_modelo = m.id_modelo AND p.codigo <> %s
                ORDER BY m.nombre, m.id_modelo, p.codigo
                """,
                (CODIGO_DETENER,),
            )
            modelos = {}
            for fila in cur.fetchall():
                codigo = fila.pop("codigo")
                invitado = fila.pop("permite_invitado")
                modelo = modelos.setdefault(fila["id_modelo"], {**fila, "codigos": [], "codigos_invitado": []})
                if codigo is not None:
                    modelo["codigos"].append(codigo)
                    if invitado and codigo in CODIGOS_EXHIBICION:
                        modelo["codigos_invitado"].append(codigo)
            return list(modelos.values())

    def guardar_capacidades(self, id_modelo, codigos, actor):
        nuevos = set(codigos) - {CODIGO_DETENER}
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute("SELECT nombre FROM modelos_vehiculo WHERE id_modelo = %s FOR UPDATE", (id_modelo,))
            modelo = cur.fetchone()
            if modelo is None:
                raise RecursoNoEncontradoError("El modelo no existe")
            cur.execute(
                "SELECT codigo FROM capacidades_modelo WHERE id_modelo = %s AND codigo <> %s",
                (id_modelo, CODIGO_DETENER),
            )
            actuales = {fila["codigo"] for fila in cur.fetchall()}
            agregados = sorted(nuevos - actuales)
            retirados = sorted(actuales - nuevos)
            if not agregados and not retirados:
                return sorted(nuevos)

            self._comprobar_reservas_modelo(cur, id_modelo)
            if agregados:
                cur.execute("SELECT DISTINCT codigo FROM comandos WHERE codigo IN %s", (tuple(agregados),))
                if {fila["codigo"] for fila in cur.fetchall()} != set(agregados):
                    raise ReglaNegocioError("Uno o más comandos no existen en el catálogo")
                cur.executemany(
                    "INSERT INTO capacidades_modelo (id_modelo, codigo) VALUES (%s, %s)",
                    [(id_modelo, codigo) for codigo in agregados],
                )
            if retirados:
                cur.execute(
                    "DELETE FROM capacidades_modelo WHERE id_modelo = %s AND codigo IN %s",
                    (id_modelo, tuple(retirados)),
                )
            AuditoriaRepository.registrar(cur, actor, "modelo.capacidades_actualizadas", {
                "id_modelo": id_modelo, "nombre": modelo["nombre"], "agregados": agregados, "retirados": retirados,
            })
            return sorted(nuevos)

    def guardar_capacidades_invitado(self, id_modelo, codigos, actor):
        if not codigos <= (CODIGOS_EXHIBICION.keys() - {CODIGO_DETENER}):
            raise ReglaNegocioError("Invitado sólo admite avance y giros")
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_modelo FROM modelos_vehiculo WHERE id_modelo = %s FOR UPDATE", (id_modelo,))
            if cur.fetchone() is None:
                raise RecursoNoEncontradoError("El modelo no existe")
            cur.execute("SELECT codigo, permite_invitado FROM capacidades_modelo WHERE id_modelo = %s", (id_modelo,))
            filas = cur.fetchall()
            if not codigos <= {fila["codigo"] for fila in filas}:
                raise ReglaNegocioError("Primero habilita los comandos en el modelo")
            anteriores = {fila["codigo"] for fila in filas if fila["permite_invitado"]}
            if anteriores != codigos:
                self._comprobar_reservas_modelo(cur, id_modelo)
                cur.executemany("UPDATE capacidades_modelo SET permite_invitado = %s WHERE id_modelo = %s AND codigo = %s",
                                [(codigo in codigos, id_modelo, codigo) for codigo in sorted(anteriores ^ codigos)])
                AuditoriaRepository.registrar(cur, actor, "modelo.exhibicion_actualizada", {
                    "id_modelo": id_modelo, "codigos": sorted(codigos),
                })
            return sorted(codigos)

    @staticmethod
    def _comprobar_reservas_modelo(cur, id_modelo):
        cur.execute("""
            SELECT 1 FROM reservas_control r JOIN inventario_unidades i
              ON i.id_vehiculo = r.id_vehiculo_reservado
            WHERE i.id_modelo = %s LIMIT 1
        """, (id_modelo,))
        if cur.fetchone() is not None:
            raise ReglaNegocioError("Hay una unidad de este modelo con una reserva de control abierta")

    @staticmethod
    def _guardar_modelo(cur, consulta, parametros):
        try:
            cur.execute(consulta, parametros)
        except IntegrityError as error:
            if error.args[0] == 1062:
                raise ReglaNegocioError("Ya existe un modelo con ese nombre") from None
            raise

    def crear_modelo(self, actor, *, nombre, descripcion):
        with self._db.transaction() as conn, conn.cursor() as cur:
            self._guardar_modelo(cur, "INSERT INTO modelos_vehiculo (nombre, descripcion) VALUES (%s, %s)",
                                 (nombre, descripcion))
            id_modelo = cur.lastrowid
            AuditoriaRepository.registrar(cur, actor, "modelo.creado", {"id_modelo": id_modelo, "nombre": nombre})
            return {"id_modelo": id_modelo, "nombre": nombre, "descripcion": descripcion, "activo": True}

    def editar_modelo(self, id_modelo, actor, *, nombre, descripcion, activo):
        with self._db.transaction() as conn, conn.cursor() as cur:
            cur.execute("SELECT nombre, descripcion, activo FROM modelos_vehiculo WHERE id_modelo = %s FOR UPDATE",
                        (id_modelo,))
            actual = cur.fetchone()
            if actual is None:
                raise RecursoNoEncontradoError("El modelo no existe")
            nuevo = {"nombre": nombre, "descripcion": descripcion, "activo": activo}
            if actual == nuevo:
                return {"id_modelo": id_modelo, **nuevo}

            accion = "modelo.editado"
            if not activo and actual["activo"]:
                cur.execute(
                    "SELECT 1 FROM inventario_unidades WHERE id_modelo = %s AND estado_comercial <> 'inactivo' LIMIT 1",
                    (id_modelo,),
                )
                if cur.fetchone() is not None:
                    raise ReglaNegocioError("Desactiva las unidades activas de este modelo antes de desactivar el modelo")
                accion = "modelo.desactivado"
            elif activo and not actual["activo"]:
                accion = "modelo.reactivado"

            self._guardar_modelo(cur, "UPDATE modelos_vehiculo SET nombre = %s, descripcion = %s, activo = %s "
                                 "WHERE id_modelo = %s", (nombre, descripcion, activo, id_modelo))
            if nombre != actual["nombre"]:
                # Los contratos de Control y Monitoreo también leen vehiculos.modelo.
                cur.execute(
                    """
                    UPDATE vehiculos v JOIN inventario_unidades i ON i.id_vehiculo = v.id_vehiculo
                    SET v.modelo = %s WHERE i.id_modelo = %s
                    """,
                    (nombre, id_modelo),
                )
            AuditoriaRepository.registrar(cur, actor, accion, {"id_modelo": id_modelo, "nombre": nombre})
            return {"id_modelo": id_modelo, **nuevo}

    @staticmethod
    def bloquear_unidad(cur, id_vehiculo):
        cur.execute(
            """
            SELECT v.*, i.id_modelo, i.estado_comercial FROM inventario_unidades i
            JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
            WHERE i.id_vehiculo = %s FOR UPDATE
            """,
            (id_vehiculo,),
        )
        unidad = cur.fetchone()
        if unidad is None:
            raise RecursoNoEncontradoError("La unidad no existe en el inventario")
        return unidad

    @staticmethod
    def comprobar_reserva(cur, id_vehiculo):
        cur.execute(
            "SELECT id_reserva FROM reservas_control WHERE id_vehiculo_reservado = %s FOR UPDATE",
            (id_vehiculo,),
        )
        if cur.fetchone() is not None:
            raise ReglaNegocioError("La unidad tiene una reserva de control abierta")

    @staticmethod
    def _consultar_modelo_para_unidad(cur, id_modelo):
        if id_modelo is None:
            return None
        cur.execute("SELECT nombre, activo FROM modelos_vehiculo WHERE id_modelo = %s FOR SHARE", (id_modelo,))
        modelo = cur.fetchone()
        if modelo is None:
            raise RecursoNoEncontradoError("El modelo no existe")
        return modelo

    @staticmethod
    def _validar_modelo_para_estado(modelo, estado):
        if estado != "inactivo" and (modelo is None or not modelo["activo"]):
            raise ReglaNegocioError("Selecciona un modelo activo para habilitar la unidad")

    @staticmethod
    def _obtener_unidad(cur, id_vehiculo):
        cur.execute(CONSULTA_INVENTARIO + " WHERE v.id_vehiculo = %s", (id_vehiculo,))
        return cur.fetchone()

    def _movimientos_modelo(self, cur, unidad):
        modelo = self._consultar_modelo_para_unidad(cur, unidad["id_modelo"])
        if not modelo or not modelo["activo"] or not unidad["activo"] or unidad["estado_comercial"] == "inactivo":
            raise ReglaNegocioError("Selecciona una unidad activa con un modelo comercial activo")
        # El catálogo comparte códigos físicos. Cada unidad conserva sus propios IDs y bajas lógicas.
        cur.execute("""
            SELECT c.codigo, MIN(c.nombre) AS nombre, destino.id_comando AS registrado
            FROM comandos c
            LEFT JOIN capacidades_modelo p ON p.codigo = c.codigo AND p.id_modelo = %s
            LEFT JOIN comandos destino ON destino.codigo = c.codigo AND destino.id_vehiculo = %s
            WHERE c.activo = TRUE AND c.codigo IN %s AND (p.codigo IS NOT NULL OR c.codigo = %s)
            GROUP BY c.codigo, destino.id_comando ORDER BY c.codigo
        """, (unidad["id_modelo"], unidad["id_vehiculo"], tuple(sorted(CODIGOS_CONTROL)), CODIGO_DETENER))
        return cur.fetchall()

    def movimientos_pendientes(self, id_vehiculo):
        with self._db.transaction() as conn, conn.cursor() as cur:
            unidad = self.bloquear_unidad(cur, id_vehiculo)
            return [fila for fila in self._movimientos_modelo(cur, unidad) if fila["registrado"] is None]

    def cargar_movimientos(self, id_vehiculo, id_modelo, codigos, actor):
        with self._db.transaction() as conn, conn.cursor() as cur:
            unidad = self.bloquear_unidad(cur, id_vehiculo)
            if unidad["id_modelo"] != id_modelo:
                raise ReglaNegocioError("El modelo de la unidad cambió. Actualiza el inventario")
            disponibles = {fila["codigo"]: fila for fila in self._movimientos_modelo(cur, unidad)}
            if not codigos <= disponibles.keys():
                raise ReglaNegocioError("La selección contiene movimientos que ya no están disponibles para el modelo")
            nuevos = sorted(codigo for codigo in codigos if disponibles[codigo]["registrado"] is None)
            if nuevos:
                self.comprobar_reserva(cur, id_vehiculo)
                try:
                    cur.executemany("INSERT INTO comandos (id_vehiculo, codigo, nombre) VALUES (%s, %s, %s)",
                                    [(id_vehiculo, codigo, disponibles[codigo]["nombre"]) for codigo in nuevos])
                except IntegrityError as error:
                    if error.args[0] == 1062:
                        raise ReglaNegocioError("Ya existe un comando con el mismo nombre o código en esta unidad") from None
                    raise
                AuditoriaRepository.registrar(cur, actor, "unidad.movimientos_cargados",
                                              {"id_modelo": id_modelo, "codigos": nuevos}, id_vehiculo)
            return nuevos

    def crear_unidad(self, actor, *, nombre, id_modelo, descripcion, microcontrolador, estado_comercial):
        with self._db.transaction() as conn, conn.cursor() as cur:
            modelo = self._consultar_modelo_para_unidad(cur, id_modelo)
            self._validar_modelo_para_estado(modelo, estado_comercial)
            id_vehiculo = self._db.call_in(conn, "sp_crear_vehiculo", (
                nombre, modelo["nombre"], descripcion, microcontrolador,
            ))[0]["id_vehiculo"]
            cur.execute(
                "INSERT INTO inventario_unidades (id_vehiculo, id_modelo, estado_comercial) VALUES (%s, %s, %s)",
                (id_vehiculo, id_modelo, estado_comercial),
            )
            if estado_comercial == "inactivo":
                cur.execute("UPDATE vehiculos SET activo = FALSE WHERE id_vehiculo = %s", (id_vehiculo,))
            AuditoriaRepository.registrar(cur, actor, "unidad.creada", {
                "id_modelo": id_modelo, "estado_comercial": estado_comercial,
            }, id_vehiculo)
            return self._obtener_unidad(cur, id_vehiculo)

    def editar_unidad(self, id_vehiculo, actor, *, nombre, id_modelo, descripcion, microcontrolador, estado_comercial):
        with self._db.transaction() as conn, conn.cursor() as cur:
            modelo = self._consultar_modelo_para_unidad(cur, id_modelo)
            actual = self.bloquear_unidad(cur, id_vehiculo)
            anterior = actual["estado_comercial"]
            estado = estado_comercial or anterior
            if anterior == "asignado" and (estado != anterior or id_modelo != actual["id_modelo"]):
                raise ReglaNegocioError("Libera la unidad antes de cambiar su modelo o estado comercial")
            self._validar_modelo_para_estado(modelo, estado)
            nombre_modelo = modelo["nombre"] if modelo else actual["modelo"]
            valores = (nombre, nombre_modelo, descripcion, microcontrolador, estado != "inactivo")
            actuales = tuple(actual[campo] for campo in ("nombre", "modelo", "descripcion", "microcontrolador", "activo"))
            if (valores, id_modelo, estado) == (actuales, actual["id_modelo"], anterior):
                return self._obtener_unidad(cur, id_vehiculo)

            self.comprobar_reserva(cur, id_vehiculo)
            self._db.call_in(conn, "sp_actualizar_vehiculo", (id_vehiculo, *valores))
            cur.execute(
                "UPDATE inventario_unidades SET id_modelo = %s, estado_comercial = %s WHERE id_vehiculo = %s",
                (id_modelo, estado, id_vehiculo),
            )
            accion = "unidad.editada"
            if estado != anterior:
                if estado == "inactivo":
                    accion = "unidad.desactivada"
                elif anterior == "inactivo":
                    accion = "unidad.reactivada"
            AuditoriaRepository.registrar(cur, actor, accion, {
                "id_modelo": id_modelo, "id_modelo_anterior": actual["id_modelo"],
                "estado_comercial": estado, "estado_anterior": anterior,
            }, id_vehiculo)
            return self._obtener_unidad(cur, id_vehiculo)

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
