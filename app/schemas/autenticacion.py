from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints


Correo = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
]
Rol = Literal["administrador", "usuario"]
MIN_LONGITUD_PASSWORD = 12
MAX_LONGITUD_PASSWORD = 128


class Credenciales(BaseModel):
    correo: Correo
    password: SecretStr = Field(min_length=1, max_length=MAX_LONGITUD_PASSWORD)

    model_config = ConfigDict(json_schema_extra={
        "examples": [{"correo": "admin@ejemplo.test", "password": "contraseña-de-tu-cuenta"}],
    })


class UsuarioOut(BaseModel):
    id_usuario: int
    correo: str
    nombre: str
    rol: Rol


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    usuario: UsuarioOut


class SesionActual(BaseModel):
    id_sesion: int
    usuario: UsuarioOut
