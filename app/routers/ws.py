import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.repositories.estado_repository import EstadoRepository
from app.repositories.vehiculo_repository import VehiculoRepository
from app.websocket.manager import Suscripcion, crear_evento, evento_estado_actual, manager

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

    canal = Suscripcion(websocket)
    try:
        estado = await asyncio.to_thread(estados.obtener, id_vehiculo)
        manager.agregar(id_vehiculo, canal)
        if not await canal.enviar_o_revalidar(evento_estado_actual(id_vehiculo, estado)):
            return
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.quitar(id_vehiculo, websocket)
