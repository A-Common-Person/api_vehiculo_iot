import argparse
from hashlib import sha256
from pathlib import Path
from secrets import token_urlsafe
import socket
import ssl

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from pymysql.err import MySQLError

from app.config import settings
from app.exceptions import RecursoNoEncontradoError, ReglaNegocioError
from app.repositories.control_repository import ControlRepository


HOST = "vehiculo-iot-erik.duckdns.org"
PUERTO = 443


def verificar_ca(ruta: Path) -> str:
    raices = x509.load_pem_x509_certificates(ruta.read_bytes())
    for raiz in raices:
        restricciones = raiz.extensions.get_extension_for_class(x509.BasicConstraints).value
        if not restricciones.ca or raiz.issuer != raiz.subject:
            raise ValueError("El archivo debe contener certificados raíz de confianza")
    pem = b"".join(raiz.public_bytes(Encoding.PEM) for raiz in raices).decode("ascii")

    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    contexto.minimum_version = contexto.maximum_version = ssl.TLSVersion.TLSv1_2
    contexto.load_verify_locations(cadata=pem)
    with socket.create_connection((HOST, PUERTO), timeout=8) as conexion:
        with contexto.wrap_socket(conexion, server_hostname=HOST):
            pass
    return pem


def main():
    parser = argparse.ArgumentParser(description="Emitir la credencial WSS de una unidad publicada")
    parser.add_argument("--unidad", type=int, required=True)
    parser.add_argument("--ca", type=Path, required=True, help="Certificado raíz PEM del sitio público")
    parser.add_argument("--salida", type=Path, required=True, help="Ruta privada para IoT43Publico.h")
    args = parser.parse_args()
    if not settings.publicacion_habilitada:
        parser.error("Ejecuta este comando con PUBLICACION_HABILITADA=true")
    if not 1 <= args.unidad <= 2_147_483_647:
        parser.error("Indica un ID de unidad válido")
    if args.salida.name != "IoT43Publico.h" or args.salida.exists():
        parser.error("La salida debe llamarse IoT43Publico.h y estar libre")

    try:
        pem = verificar_ca(args.ca)
    except (OSError, ValueError, x509.ExtensionNotFound) as error:
        parser.exit(1, f"No se pudo verificar el TLS del servidor público: {error}.\n")

    token = token_urlsafe(32)
    try:
        with args.salida.open("x", encoding="ascii") as archivo:
            archivo.write(f'''#pragma once
#define IOT43_HOST "{HOST}"
#define IOT43_PUERTO {PUERTO}
#define IOT43_UNIDAD {args.unidad}
#define IOT43_TOKEN "{token}"
static const char IOT43_CA_PEM[] = R"CA({pem})CA";
''')
    except OSError as error:
        parser.exit(1, f"No se pudo escribir el encabezado: {error}.\n")

    try:
        ControlRepository().emitir_credencial(
            args.unidad, sha256(token.encode("ascii")).digest(), exigir_sin_reserva=True,
        )
    except (RecursoNoEncontradoError, ReglaNegocioError) as error:
        args.salida.unlink(missing_ok=True)
        parser.exit(1, f"No se emitió la credencial: {error}.\n")
    except MySQLError:
        parser.exit(1, "No se confirmó el registro en MySQL. Conserva el archivo en privado y verifica la unidad.\n")
    print(f"Credencial emitida para la unidad {args.unidad}. Encabezado privado en {args.salida}.")


if __name__ == "__main__":
    main()
