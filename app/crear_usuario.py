import argparse
from getpass import GetPassWarning, getpass
from warnings import simplefilter

from pydantic import TypeAdapter, ValidationError
from pymysql.err import IntegrityError, MySQLError

from app.config import settings
from app.repositories.sesion_repository import SesionRepository
from app.schemas.autenticacion import Correo, MAX_LONGITUD_PASSWORD, MIN_LONGITUD_PASSWORD
from app.services.autenticacion_service import hash_password


def main():
    parser = argparse.ArgumentParser(description="Crear una cuenta de Administración en la copia de RDS")
    parser.add_argument("--rol", required=True, choices=["administrador", "usuario"])
    args = parser.parse_args()
    if not settings.administracion_habilitada or not settings.db_host.startswith("instancia-rds-iot-43-pruebas."):
        parser.exit(1, "Este comando requiere la instancia RDS de pruebas y la administración habilitada.\n")

    nombre = input("Nombre para mostrar: ").strip()
    if not nombre or len(nombre) > 120:
        parser.exit(1, "El nombre debe contener entre 1 y 120 caracteres.\n")
    try:
        correo = TypeAdapter(Correo).validate_python(input("Correo de la cuenta: "))
    except ValidationError:
        parser.exit(1, "El correo no tiene un formato válido.\n")

    simplefilter("error", GetPassWarning)
    try:
        password = getpass("Contraseña nueva de la cuenta: ")
        if not MIN_LONGITUD_PASSWORD <= len(password) <= MAX_LONGITUD_PASSWORD:
            parser.exit(
                1, f"La contraseña debe tener entre {MIN_LONGITUD_PASSWORD} y {MAX_LONGITUD_PASSWORD} caracteres.\n"
            )
        if password != getpass("Repite la contraseña nueva: "):
            parser.exit(1, "Las contraseñas son distintas.\n")
    except GetPassWarning:
        parser.exit(1, "Abre una terminal interactiva para introducir la contraseña de forma oculta.\n")

    try:
        identificador = SesionRepository().crear_usuario(correo, nombre, args.rol, hash_password(password))
    except IntegrityError as exc:
        if exc.args[0] != 1062:
            raise
        parser.exit(1, "Ya existe una cuenta con ese correo.\n")
    except MySQLError as exc:
        parser.exit(1, f"No se pudo crear la cuenta en MySQL (código {exc.args[0]}).\n")
    print(f"Cuenta de pruebas creada. ID {identificador}, rol {args.rol}.")


if __name__ == "__main__":
    main()
