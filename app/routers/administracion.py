from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from app.dependencias_autenticacion import administrador, sesion_actual
from app.repositories.asignacion_repository import AsignacionRepository
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.inventario_repository import inventario
from app.repositories.sesion_repository import SesionRepository
from app.schemas.administracion import (
    AltaCliente,
    AsignacionOut,
    AsignarUnidad,
    ClienteOut,
    EventoAuditoriaOut,
    UnidadInventarioOut,
)
from app.schemas.autenticacion import SesionActual
from app.schemas.consultas import VehiculoOut
from app.services.autenticacion_service import hash_password


router = APIRouter(
    tags=["Administración"],
    responses={401: {"description": "Falta una sesión vigente"}, 403: {"description": "Permiso insuficiente"}},
)
clientes = SesionRepository()
asignaciones = AsignacionRepository()
auditoria = AuditoriaRepository()

UnidadId = Annotated[int, Path(gt=0, le=2**31 - 1)]
Limite = Annotated[int, Query(ge=1, le=100)]
Desplazamiento = Annotated[int, Query(ge=0, le=2**31 - 1)]
Administrador = Annotated[SesionActual, Depends(administrador)]


@router.get(
    "/administracion/inventario", response_model=list[UnidadInventarioOut], dependencies=[Depends(administrador)]
)
def ver_inventario():
    return inventario.listar()


@router.get("/administracion/clientes", response_model=list[ClienteOut], dependencies=[Depends(administrador)])
def listar_clientes(limite: Limite = 50, desplazamiento: Desplazamiento = 0):
    return clientes.listar_clientes(limite, desplazamiento)


@router.post(
    "/administracion/clientes", status_code=201, response_model=ClienteOut,
    responses={409: {"description": "El correo ya está registrado"}},
)
def crear_cliente(datos: AltaCliente, sesion: Administrador):
    rol = "usuario"
    id_usuario = clientes.crear_usuario(
        datos.correo, datos.nombre, rol, hash_password(datos.password.get_secret_value()),
        creado_por=sesion.usuario.id_usuario,
    )
    return ClienteOut(id_usuario=id_usuario, correo=datos.correo, nombre=datos.nombre, rol=rol, activo=True)


@router.get(
    "/administracion/unidades/{id_vehiculo}/asignaciones",
    response_model=list[AsignacionOut],
    dependencies=[Depends(administrador)],
    responses={404: {"description": "La unidad no existe en el inventario"}},
)
def historial_asignaciones(id_vehiculo: UnidadId, limite: Limite = 50, desplazamiento: Desplazamiento = 0):
    return asignaciones.historial(id_vehiculo, limite, desplazamiento)


@router.put(
    "/administracion/unidades/{id_vehiculo}/asignacion", response_model=AsignacionOut,
    responses={
        404: {"description": "La unidad o el cliente no existe"},
        409: {"description": "La asignación cambió o la unidad o el cliente no están disponibles"},
    },
)
def asignar_unidad(id_vehiculo: UnidadId, datos: AsignarUnidad, sesion: Administrador):
    return asignaciones.asignar(
        id_vehiculo, datos.id_usuario, datos.id_asignacion_esperada, sesion.usuario.id_usuario
    )


@router.delete(
    "/administracion/unidades/{id_vehiculo}/asignacion", status_code=204,
    responses={
        404: {"description": "La unidad no existe en el inventario"},
        409: {"description": "La asignación cambió o hay una reserva de control abierta"},
    },
)
def liberar_unidad(
    id_vehiculo: UnidadId,
    sesion: Administrador,
    id_asignacion_esperada: Annotated[int, Query(gt=0, le=2**64 - 1)],
):
    asignaciones.liberar(id_vehiculo, id_asignacion_esperada, sesion.usuario.id_usuario)
    return Response(status_code=204)


@router.get(
    "/administracion/auditoria", response_model=list[EventoAuditoriaOut], dependencies=[Depends(administrador)]
)
def consultar_auditoria(
    id_vehiculo: Annotated[int | None, Query(gt=0, le=2**31 - 1)] = None,
    limite: Limite = 50,
    desplazamiento: Desplazamiento = 0,
):
    return auditoria.listar(id_vehiculo, limite, desplazamiento)


@router.get("/vehiculos/mios", response_model=list[VehiculoOut], tags=["Vehículos"])
def mis_vehiculos(sesion: SesionActual = Depends(sesion_actual)):
    if sesion.usuario.rol != "usuario":
        raise HTTPException(status_code=403, detail="Se requiere el rol Usuario")
    return inventario.listar_asignados(sesion.usuario.id_usuario)
