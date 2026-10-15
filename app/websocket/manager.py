from datetime import datetime, timezone

from fastapi import WebSocket


def crear_evento(evento, id_vehiculo, comando=None, codigo=None, **extra):
    return {
        "evento": evento,
        "id_vehiculo": id_vehiculo,
        "comando": comando,
        "codigo": codigo,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


class ConnectionManager:
    def __init__(self):
        self._conexiones: dict[int, list[WebSocket]] = {}

    def agregar(self, id_vehiculo: int, websocket: WebSocket):
        self._conexiones.setdefault(id_vehiculo, []).append(websocket)

    def quitar(self, id_vehiculo: int, websocket: WebSocket):
        lista = self._conexiones.get(id_vehiculo, [])
        if websocket in lista:
            lista.remove(websocket)
        if not lista:
            self._conexiones.pop(id_vehiculo, None)

    async def difundir(self, id_vehiculo: int, mensaje: dict):
        for websocket in list(self._conexiones.get(id_vehiculo, [])):
            try:
                await websocket.send_json(mensaje)
            except Exception:
                self.quitar(id_vehiculo, websocket)


manager = ConnectionManager()