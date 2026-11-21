from hashlib import pbkdf2_hmac, sha256
import re
from secrets import compare_digest, token_bytes, token_urlsafe

from app.repositories.sesion_repository import SesionRepository
from app.schemas.autenticacion import SesionActual, TokenOut, UsuarioOut


ITERACIONES = 600_000
DURACION_SESION = 8 * 60 * 60
FORMATO_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


def _derivar(password, salt):
    return pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERACIONES)


def hash_password(password):
    salt = token_bytes(16)
    return f"pbkdf2_sha256${ITERACIONES}${salt.hex()}${_derivar(password, salt).hex()}"


def _verificar_password(password, guardado):
    try:
        algoritmo, iteraciones, salt_hex, hash_hex = guardado.split("$")
        salt, esperado = bytes.fromhex(salt_hex), bytes.fromhex(hash_hex)
    except ValueError:
        return False
    if algoritmo != "pbkdf2_sha256" or iteraciones != str(ITERACIONES) or len(salt) != 16 or len(esperado) != 32:
        return False
    return compare_digest(_derivar(password, salt), esperado)


HASH_FICTICIO = hash_password(token_urlsafe(32))


class AutenticacionService:
    def __init__(self, sesiones=None):
        self.sesiones = sesiones if sesiones is not None else SesionRepository()

    def iniciar(self, credenciales):
        usuario = self.sesiones.obtener_usuario(credenciales.correo)
        guardado = usuario["password_hash"] if usuario and usuario["activo"] else HASH_FICTICIO
        valida = _verificar_password(credenciales.password.get_secret_value(), guardado)
        if not valida or not usuario or not usuario["activo"]:
            return None
        token = token_urlsafe(32)
        if not self.sesiones.crear_sesion(
            usuario["id_usuario"], guardado, sha256(token.encode("ascii")).digest(), DURACION_SESION
        ):
            return None
        return TokenOut(
            access_token=token, expires_in=DURACION_SESION, usuario=UsuarioOut.model_validate(usuario)
        )

    def identificar(self, token):
        if not FORMATO_TOKEN.fullmatch(token):
            return None
        fila = self.sesiones.obtener_sesion(sha256(token.encode("ascii")).digest())
        if fila is None:
            return None
        return SesionActual(id_sesion=fila["id_sesion"], usuario=UsuarioOut.model_validate(fila))

    def cerrar(self, sesion):
        self.sesiones.revocar_sesion(sesion.id_sesion)
