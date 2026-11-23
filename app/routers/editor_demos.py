from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response

from app.dependencias_autenticacion import sesion_actual
from app.repositories.editor_demo_repository import EdicionDemoNoAutorizada, EditorDemoRepository
from app.schemas.autenticacion import SesionActual
from app.schemas.demo import DemoEditableIn, DemoEditableOut, EditorDemoOut, MovimientoPersonalizadoIn, MovimientoPersonalizadoOut


router = APIRouter(prefix="/vehiculos/{id_vehiculo}/demos/editor", tags=["Editor de demos"])
repositorio = EditorDemoRepository()
Unidad = Annotated[int, Path(gt=0, le=2**31 - 1)]
Demo = Annotated[int, Path(gt=0, le=2**31 - 1)]
Sesion = Annotated[SesionActual, Depends(sesion_actual)]


def editar(operacion, *argumentos):
    try:
        return operacion(*argumentos)
    except EdicionDemoNoAutorizada:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar demos en esta unidad") from None


@router.get("", response_model=EditorDemoOut)
def listar_editor(id_vehiculo: Unidad, sesion: Sesion):
    return editar(repositorio.contexto, id_vehiculo, sesion)


@router.post("/movimientos", response_model=MovimientoPersonalizadoOut, status_code=201)
def crear_movimiento(id_vehiculo: Unidad, datos: MovimientoPersonalizadoIn, sesion: Sesion):
    return editar(repositorio.editar_movimiento, id_vehiculo, sesion, datos)


@router.put("/movimientos/{id_movimiento}", response_model=MovimientoPersonalizadoOut)
def actualizar_movimiento(id_vehiculo: Unidad, id_movimiento: Demo, datos: MovimientoPersonalizadoIn, sesion: Sesion):
    return editar(repositorio.editar_movimiento, id_vehiculo, sesion, datos, id_movimiento)


@router.delete("/movimientos/{id_movimiento}", status_code=204)
def borrar_movimiento(id_vehiculo: Unidad, id_movimiento: Demo, sesion: Sesion):
    editar(repositorio.editar_movimiento, id_vehiculo, sesion, None, id_movimiento)
    return Response(status_code=204)


@router.get("/{id_demo}", response_model=DemoEditableOut)
def abrir_demo(id_vehiculo: Unidad, id_demo: Demo, sesion: Sesion):
    return editar(repositorio.obtener, id_vehiculo, sesion, id_demo)


@router.post("", response_model=DemoEditableOut, status_code=201)
def crear_demo(id_vehiculo: Unidad, datos: DemoEditableIn, sesion: Sesion):
    return editar(repositorio.guardar, id_vehiculo, sesion, datos)


@router.put("/{id_demo}", response_model=DemoEditableOut)
def actualizar_demo(id_vehiculo: Unidad, id_demo: Demo, datos: DemoEditableIn, sesion: Sesion):
    return editar(repositorio.guardar, id_vehiculo, sesion, datos, id_demo)
