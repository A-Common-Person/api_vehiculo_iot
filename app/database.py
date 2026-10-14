import pymysql
from contextlib import contextmanager
from pymysql.cursors import DictCursor

from app.config import settings


class Database:
    def _connect(self):
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