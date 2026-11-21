from fastapi import Depends, HTTPException, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.repositories.inventario_repository import inventario
from app.schemas.autenticacion import SesionActual
from app.services.autenticacion_service import AutenticacionService


autenticacion = AutenticacionService()
bearer = HTTPBearer(auto_error=False, scheme_name="SesionIoT")


def no_autenticado(mensaje="Se requiere una sesión vigente"):
    return HTTPException(status_code=401, detail=mensaje, headers={"WWW-Authenticate": "Bearer"})


def sesion_actual(credenciales: HTTPAuthorizationCredentials | None = Depends(bearer)) -> SesionActual:
    sesion = autenticacion.identificar(credenciales.credentials) if credenciales else None
    if sesion is None:
        raise no_autenticado()
    return sesion


def administrador(sesion: SesionActual = Depends(sesion_actual)) -> SesionActual:
    if sesion.usuario.rol != "administrador":
        raise HTTPException(status_code=403, detail="Se requiere el rol Administrador")
    return sesion


def sesion_consulta(credenciales: HTTPAuthorizationCredentials | None = Depends(bearer)) -> SesionActual | None:
    if settings.administracion_habilitada:
        return sesion_actual(credenciales)
    return None


def lectura_vehiculo(
    id_vehiculo: int = Path(gt=0, description="ID del vehículo"),
    sesion: SesionActual | None = Depends(sesion_consulta),
) -> SesionActual | None:
    if sesion is not None and not inventario.puede_consultar(id_vehiculo, sesion.usuario):
        raise HTTPException(status_code=403, detail="No tienes acceso a este vehículo")
    return sesion
