import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from app.dependencias_autenticacion import administrador, sesion_actual
from app.repositories.asignacion_repository import AsignacionRepository
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.comando_repository import CODIGO_DETENER, ComandoRepository
from app.repositories.inventario_repository import inventario
from app.repositories.sesion_repository import SesionRepository
from app.schemas.administracion import (
    AltaCliente,
    AltaModelo,
    AltaUnidad,
    AsignacionOut,
    AsignarUnidad,
    CapacidadOut,
    CargaMovimientos,
    CambiosMovimientos,
    MovimientoUnidadOut,
    ClienteOut,
    EditarModelo,
    EditarUnidad,
    EventoAuditoriaOut,
    GuardarCapacidades,
    ModeloCatalogoOut,
    ModeloOut,
    UnidadInventarioOut,
)
from app.schemas.autenticacion import SesionActual
from app.schemas.consultas import VehiculoOut
from app.services.autenticacion_service import hash_password
from app.websocket.manager import manager


router = APIRouter(
    tags=["Administración"],
    responses={401: {"description": "Falta una sesión vigente"}, 403: {"description": "Permiso insuficiente"}},
)
clientes = SesionRepository()
asignaciones = AsignacionRepository()
auditoria = AuditoriaRepository()
comandos = ComandoRepository()

UnidadId = Annotated[int, Path(gt=0, le=2**31 - 1)]
ModeloId = Annotated[int, Path(gt=0, le=2**31 - 1)]
Limite = Annotated[int, Query(ge=1, le=100)]
Desplazamiento = Annotated[int, Query(ge=0, le=2**31 - 1)]
Administrador = Annotated[SesionActual, Depends(administrador)]


@router.get(
    "/administracion/inventario", response_model=list[UnidadInventarioOut], dependencies=[Depends(administrador)]
)
def ver_inventario():
    return inventario.listar()


@router.get("/administracion/modelos", response_model=list[ModeloCatalogoOut], dependencies=[Depends(administrador)])
def listar_modelos():
    return inventario.listar_modelos()


@router.get("/administracion/capacidades", response_model=list[CapacidadOut], dependencies=[Depends(administrador)])
def listar_capacidades():
    return [comando for comando in comandos.catalogo_codigos() if comando["codigo"] != CODIGO_DETENER]


@router.put(
    "/administracion/modelos/{id_modelo}/capacidades", response_model=list[int],
    responses={404: {"description": "El modelo no existe"}, 409: {"description": "Comando desconocido o reserva activa"}},
)
def editar_capacidades(id_modelo: ModeloId, datos: GuardarCapacidades, sesion: Administrador):
    return inventario.guardar_capacidades(id_modelo, datos.codigos, sesion.usuario.id_usuario)


@router.put("/administracion/modelos/{id_modelo}/capacidades-invitado", response_model=list[int])
def editar_capacidades_invitado(id_modelo: ModeloId, datos: GuardarCapacidades, sesion: Administrador):
    return inventario.guardar_capacidades_invitado(id_modelo, datos.codigos, sesion.usuario.id_usuario)


@router.post(
    "/administracion/modelos", status_code=201, response_model=ModeloOut,
    responses={409: {"description": "Ya existe un modelo con ese nombre"}},
)
def crear_modelo(datos: AltaModelo, sesion: Administrador):
    return inventario.crear_modelo(sesion.usuario.id_usuario, **datos.model_dump())


@router.put(
    "/administracion/modelos/{id_modelo}", response_model=ModeloOut,
    responses={
        404: {"description": "El modelo no existe"},
        409: {"description": "Nombre duplicado o modelo con unidades activas"},
    },
)
def editar_modelo(id_modelo: ModeloId, datos: EditarModelo, sesion: Administrador):
    return inventario.editar_modelo(id_modelo, sesion.usuario.id_usuario, **datos.model_dump())


@router.post(
    "/administracion/unidades", status_code=201, response_model=UnidadInventarioOut,
    responses={404: {"description": "El modelo no existe"}, 409: {"description": "El modelo está inactivo"}},
)
def crear_unidad(datos: AltaUnidad, sesion: Administrador):
    return inventario.crear_unidad(sesion.usuario.id_usuario, **datos.model_dump())


@router.put(
    "/administracion/unidades/{id_vehiculo}", response_model=UnidadInventarioOut,
    responses={
        404: {"description": "La unidad o el modelo no existen"},
        409: {"description": "El estado, modelo, asignación o reserva impiden el cambio"},
    },
)
async def editar_unidad(id_vehiculo: UnidadId, datos: EditarUnidad, sesion: Administrador):
    resultado = await asyncio.to_thread(
        inventario.editar_unidad, id_vehiculo, sesion.usuario.id_usuario, **datos.model_dump()
    )
    await manager.revalidar_unidad(id_vehiculo)
    return resultado


@router.get("/administracion/unidades/{id_vehiculo}/movimientos-modelo", response_model=list[CapacidadOut],
            dependencies=[Depends(administrador)], summary="Ver movimientos del modelo que faltan en la unidad")
def movimientos_pendientes(id_vehiculo: UnidadId):
    return inventario.movimientos_pendientes(id_vehiculo)


@router.put("/administracion/unidades/{id_vehiculo}/movimientos-modelo", response_model=list[int],
            summary="Registrar los movimientos seleccionados sin ejecutar el vehículo")
def cargar_movimientos(id_vehiculo: UnidadId, datos: CargaMovimientos, sesion: Administrador):
    return inventario.cargar_movimientos(id_vehiculo, datos.id_modelo, datos.codigos, sesion.usuario.id_usuario)


@router.get("/administracion/unidades/{id_vehiculo}/movimientos-modelo/seleccion",
            response_model=list[MovimientoUnidadOut], dependencies=[Depends(administrador)])
def consultar_seleccion(id_vehiculo: UnidadId):
    return inventario.seleccion_movimientos(id_vehiculo)


@router.put("/administracion/unidades/{id_vehiculo}/movimientos-modelo/seleccion", response_model=list[int])
def guardar_seleccion(id_vehiculo: UnidadId, datos: CambiosMovimientos, sesion: Administrador):
    return inventario.cambiar_movimientos(id_vehiculo, datos, sesion.usuario.id_usuario)


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
async def asignar_unidad(id_vehiculo: UnidadId, datos: AsignarUnidad, sesion: Administrador):
    resultado = await asyncio.to_thread(
        asignaciones.asignar, id_vehiculo, datos.id_usuario, datos.id_asignacion_esperada, sesion.usuario.id_usuario
    )
    await manager.revalidar_unidad(id_vehiculo)
    return resultado


@router.delete(
    "/administracion/unidades/{id_vehiculo}/asignacion", status_code=204,
    responses={
        404: {"description": "La unidad no existe en el inventario"},
        409: {"description": "La asignación cambió o hay una reserva de control abierta"},
    },
)
async def liberar_unidad(
    id_vehiculo: UnidadId,
    sesion: Administrador,
    id_asignacion_esperada: Annotated[int, Query(gt=0, le=2**64 - 1)],
):
    await asyncio.to_thread(
        asignaciones.liberar, id_vehiculo, id_asignacion_esperada, sesion.usuario.id_usuario
    )
    await manager.revalidar_unidad(id_vehiculo)
    return Response(status_code=204)


@router.get(
    "/administracion/auditoria", response_model=list[EventoAuditoriaOut], dependencies=[Depends(administrador)]
)
def consultar_auditoria(
    id_vehiculo: Annotated[int | None, Query(gt=0, le=2**31 - 1)] = None,
    limite: Limite = 50,
    desplazamiento: Desplazamiento = 0,
    antes_de: Annotated[int | None, Query(gt=0)] = None,
    despues_de: Annotated[int | None, Query(gt=0)] = None,
):
    if antes_de is not None and despues_de is not None:
        raise HTTPException(status_code=422, detail="Elige una sola dirección de consulta")
    return auditoria.listar(id_vehiculo, limite, desplazamiento, antes_de, despues_de)


@router.get("/vehiculos/mios", response_model=list[VehiculoOut], tags=["Vehículos"])
def mis_vehiculos(sesion: SesionActual = Depends(sesion_actual)):
    if sesion.usuario.rol != "usuario":
        raise HTTPException(status_code=403, detail="Se requiere el rol Usuario")
    return inventario.listar_asignados(sesion.usuario.id_usuario)
