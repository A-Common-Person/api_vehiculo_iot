from contextlib import contextmanager
from functools import cache
from ssl import create_default_context

import pymysql
from pymysql.cursors import DictCursor

from app.config import settings


@cache
def _contexto_tls(ca):
    return create_default_context(cafile=str(ca))


class Database:
    def _connect(self, *, autocommit=False):
        administracion = settings.administracion_habilitada
        tls = _contexto_tls(settings.db_ssl_ca) if settings.db_ssl_ca else None
        return pymysql.connect(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=autocommit,
            connect_timeout=5 if administracion else 10,
            read_timeout=5 if administracion else None,
            write_timeout=5 if administracion else None,
            ssl=tls,
            binary_prefix=True,
            init_command="SET time_zone = '+00:00'" if administracion else None,
        )

    def ping(self):
        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                return True
            finally:
                conn.close()
        except Exception:
            return False

    def call_procedure(self, name, args=()):
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.callproc(name, args)
                rows = cur.fetchall()
            conn.commit()
            return rows
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def lectura(self):
        conn = self._connect(autocommit=True)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def call_in(conn, name, args=()):
        with conn.cursor() as cur:
            cur.callproc(name, args)
            return cur.fetchall()

db = Database()
