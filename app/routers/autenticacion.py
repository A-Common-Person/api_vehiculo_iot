from fastapi import APIRouter, Depends, Response

from app.dependencias_autenticacion import autenticacion, no_autenticado, sesion_actual
from app.schemas.autenticacion import Credenciales, SesionActual, TokenOut, UsuarioOut


router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login", response_model=TokenOut)
def iniciar_sesion(credenciales: Credenciales, response: Response):
    resultado = autenticacion.iniciar(credenciales)
    if resultado is None:
        raise no_autenticado("Correo o contraseña incorrectos")
    response.headers["Cache-Control"] = "no-store"
    return resultado


@router.get("/me", response_model=UsuarioOut)
def mi_sesion(response: Response, sesion: SesionActual = Depends(sesion_actual)):
    response.headers["Cache-Control"] = "no-store"
    return sesion.usuario


@router.post("/logout", status_code=204)
def cerrar_sesion(sesion: SesionActual = Depends(sesion_actual)):
    autenticacion.cerrar(sesion)
    return Response(status_code=204)
