import json
from getpass import GetPassWarning, getpass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from warnings import simplefilter

from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect


ORIGEN_LOCAL = "http://127.0.0.1:8001"
URL_WS = "ws://127.0.0.1:8001/ws/vehiculos"


def _solicitar(ruta, *, cuerpo=None, token=None):
    headers = {}
    datos = None
    if cuerpo is not None:
        headers["Content-Type"] = "application/json"
        datos = json.dumps(cuerpo).encode("utf-8")
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(ORIGEN_LOCAL + ruta, data=datos, headers=headers, method="POST"), timeout=10) as respuesta:
        return json.load(respuesta) if respuesta.status != 204 else None


def main():
    simplefilter("error", GetPassWarning)
    correo = input("Correo de tu cuenta de la aplicación: ").strip()
    try:
        password = getpass("Contraseña de tu cuenta de la aplicación: ")
    except GetPassWarning:
        print("Abre una terminal interactiva para ingresar la contraseña de forma oculta.")
        return
    try:
        vehiculo = int(input("ID del vehículo [1]: ").strip() or "1")
        if not 1 <= vehiculo < 2**31:
            raise ValueError
    except ValueError:
        print("El identificador debe ser un número entero positivo.")
        return

    try:
        token = _solicitar("/auth/login", cuerpo={"correo": correo, "password": password})["access_token"]
    except HTTPError as error:
        print(f"El inicio de sesión devolvió HTTP {error.code}.")
        return
    except (URLError, TimeoutError):
        print("No se pudo conectar con FastAPI en 127.0.0.1:8001.")
        return

    try:
        with connect(f"{URL_WS}/{vehiculo}", origin=ORIGEN_LOCAL, open_timeout=5, max_size=8192) as canal:
            canal.send(json.dumps({"tipo": "autenticar", "token": token}))
            print(canal.recv(timeout=12))
            print("Canal autorizado. Conserva esta terminal abierta para probar una reasignación o Ctrl+C para salir.")
            while True:
                print(canal.recv())
    except KeyboardInterrupt:
        print("\nPrueba finalizada.")
    except ConnectionClosed as error:
        if error.rcvd is not None:
            print(f"Canal cerrado ({error.rcvd.code}). {error.rcvd.reason}")
        else:
            print("Se perdió la conexión con FastAPI.")
    except InvalidStatus as error:
        print(f"El servidor rechazó el enlace WebSocket con HTTP {error.response.status_code}.")
    except (OSError, TimeoutError):
        print("No se pudo completar la conexión WebSocket local.")
    finally:
        try:
            _solicitar("/auth/logout", token=token)
        except (URLError, TimeoutError):
            pass


if __name__ == "__main__":
    main()
