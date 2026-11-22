import argparse
import asyncio
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from ipaddress import IPv4Address, IPv4Network
import os
from pathlib import Path
from secrets import token_urlsafe
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import uvicorn

from app.config import settings
from app.main import app
from app.repositories.control_repository import ControlRepository


PUERTO_DISPOSITIVO = 8443
UNIDAD = 1
REDES_LAN = tuple(IPv4Network(red) for red in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def carpeta_local(ip):
    return Path(os.environ["LOCALAPPDATA"]) / "IoT43" / str(ip)


def preparar(ip, destino, privado, publico):
    if not destino.parent.is_dir():
        raise SystemExit("No se encontró la carpeta del sketch Carrito_WS.")

    llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(ip))])
    ahora = datetime.now(timezone.utc)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(nombre).issuer_name(nombre).public_key(llave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - timedelta(minutes=5))
        .not_valid_after(ahora + timedelta(days=60))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip)]), critical=False)
        .sign(llave, hashes.SHA256())
    )
    privado.parent.mkdir(parents=True, exist_ok=True)
    privado.write_bytes(llave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ))
    publico.write_bytes(certificado.public_bytes(serialization.Encoding.PEM))
    # La biblioteca BearSSL del ESP8266 acepta una huella de certificado de 20 bytes.
    huella = ", ".join(f"0x{byte:02x}" for byte in certificado.fingerprint(hashes.SHA1()))
    token = token_urlsafe(32)
    ControlRepository().emitir_credencial(UNIDAD, sha256(token.encode("ascii")).digest())
    destino.write_text(
        "#pragma once\n"
        f'constexpr char IOT43_HOST[] = "{ip}";\n'
        f"constexpr uint16_t IOT43_PUERTO = {PUERTO_DISPOSITIVO};\n"
        f"constexpr uint16_t IOT43_UNIDAD = {UNIDAD};\n"
        f'constexpr char IOT43_TOKEN[] = "{token}";\n'
        f"constexpr uint8_t IOT43_HUELLA[20] = {{{huella}}};\n",
        encoding="ascii",
    )
    print(f"Archivo local creado: {destino}", flush=True)


async def solo_dispositivos(scope, receive, send):
    if scope["type"] == "websocket":
        if scope["path"].startswith("/ws/dispositivos/"):
            await app(scope, receive, send)
        else:
            await send({"type": "websocket.close", "code": 1008})
    elif scope["type"] == "http":
        await send({"type": "http.response.start", "status": 404, "headers": []})
        await send({"type": "http.response.body", "body": b""})


class ServidorLAN(uvicorn.Server):
    def capture_signals(self):
        return nullcontext()


async def servir(ip, privado, publico):
    opciones = dict(ws_max_size=4096, ws_max_queue=4, ws_per_message_deflate=False, proxy_headers=False)
    lan = ServidorLAN(uvicorn.Config(
        solo_dispositivos, host=str(ip), port=PUERTO_DISPOSITIVO, lifespan="off",
        ssl_keyfile=str(privado), ssl_certfile=str(publico), **opciones,
    ))
    local = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8001, **opciones))
    tareas = [asyncio.create_task(servidor.serve()) for servidor in (lan, local)]
    try:
        await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
    finally:
        local.should_exit = lan.should_exit = True
        await asyncio.gather(*tareas)


def main():
    parser = argparse.ArgumentParser(description="Prueba local con el ESP8266 de la unidad 1")
    parser.add_argument("--ip-red-local", type=IPv4Address, required=True)
    parser.add_argument("--preparar-archivo", type=Path)
    args = parser.parse_args()
    ip = args.ip_red_local
    if not any(ip in red for red in REDES_LAN):
        parser.error("Indica la IPv4 privada de esta computadora en la red Wi-Fi del ESP8266.")
    if not settings.administracion_habilitada or not settings.db_host.startswith("instancia-rds-iot-43-pruebas."):
        parser.error("Se requiere la base de datos de pruebas de la actividad 4.3.")
    with socket.socket() as direccion:
        try:
            direccion.bind((str(ip), 0))
        except OSError:
            parser.error("La IPv4 no está asignada a esta computadora. Revísala con ipconfig.")

    carpeta = carpeta_local(ip)
    privado, publico = carpeta / "llave.pem", carpeta / "certificado.pem"
    if args.preparar_archivo:
        preparar(ip, args.preparar_archivo, privado, publico)
    elif not privado.is_file() or not publico.is_file():
        parser.error("Prepara primero el ESP8266 para esta IPv4 con -PrepararDispositivo.")
    elif x509.load_pem_x509_certificate(publico.read_bytes()).not_valid_after_utc <= datetime.now(timezone.utc):
        parser.error("El certificado venció. Ejecuta -PrepararDispositivo y vuelve a cargar el sketch.")
    asyncio.run(servir(ip, privado, publico))


if __name__ == "__main__":
    main()
