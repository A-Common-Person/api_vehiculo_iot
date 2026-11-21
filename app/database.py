from contextlib import contextmanager
from ssl import create_default_context

import pymysql
from pymysql.cursors import DictCursor

from app.config import settings


class Database:
    def _connect(self):
        tls = None
        if settings.db_ssl_ca is not None:
            tls = create_default_context(cafile=str(settings.db_ssl_ca))
        return pymysql.connect(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
            connect_timeout=10,
            ssl=tls,
            binary_prefix=True,
            init_command="SET time_zone = '+00:00'" if settings.administracion_habilitada else None,
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
