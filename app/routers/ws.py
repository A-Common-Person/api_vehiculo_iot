import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.repositories.estado_repository import EstadoRepository
from app.repositories.vehiculo_repository import VehiculoRepository
from app.websocket.manager import crear_evento, manager

router = APIRouter()
vehiculos = VehiculoRepository()
estados = EstadoRepository()


@router.websocket("/ws/vehiculos/{id_vehiculo}")
async def monitorear_vehiculo(websocket: WebSocket, id_vehiculo: int):
    await websocket.accept()

    vehiculo = await asyncio.to_thread(vehiculos.obtener_por_id, id_vehiculo)
    if vehiculo is None:
        await websocket.send_json(
            crear_evento("error", id_vehiculo, mensaje="El vehículo no existe")
        )
        await websocket.close(code=4404)
        return

    manager.agregar(id_vehiculo, websocket)
    try:
        estado = await asyncio.to_thread(estados.obtener, id_vehiculo)
        await websocket.send_json(
            crear_evento(
                "estado_actual",
                id_vehiculo,
                comando=estado["comando"] if estado else None,
                codigo=estado["codigo"] if estado else None,
                conectado=bool(estado["conectado"]) if estado else False,
            )
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.quitar(id_vehiculo, websocket)