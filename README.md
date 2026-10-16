# API Vehículo IoT (entorno Dev local)

API en Python con FastAPI y programación orientada a objetos para controlar y monitorear un vehículo IoT (excavadora). Usa los 21 Stored Procedures del esquema `vehiculo_iot` alojado en Amazon RDS y transmite eventos en tiempo real por WebSocket. Se ejecuta únicamente en `localhost:8000`.

## Requisitos

- Python 3.11 o superior
- Una instancia de Amazon RDS (MySQL) con la base `vehiculo_iot` y sus 21 Stored Procedures
- Regla de Security Group MySQL TCP 3306 restringida a tu IP

## Instalación y ejecución local

```powershell
git clone https://github.com/A-Common-Person/api_vehiculo_iot
cd api-vehiculo-iot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edita `.env` con tus datos (nunca lo subas a GitHub) y arranca el servidor:

```powershell
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- Salud: http://localhost:8000/health

## Configuración (`.env`)

| Variable      | Descripción                                                 |
| ------------- | ----------------------------------------------------------- |
| `DB_HOST`     | Endpoint de Amazon RDS                                      |
| `DB_PORT`     | Puerto MySQL (3306)                                         |
| `DB_USER`     | Usuario de MySQL (preferentemente solo con permiso EXECUTE) |
| `DB_PASSWORD` | Contraseña del usuario                                      |
| `DB_NAME`     | Nombre del esquema (`vehiculo_iot`)                         |
| `API_KEY`     | Clave para las operaciones de eliminación y control de DEMO |

## Arquitectura

```
app/
├── main.py              # aplicación FastAPI y manejo de errores
├── config.py            # Settings (lee .env)
├── database.py          # Database: conexión, llamadas a SP y transacciones
├── exceptions.py        # errores de negocio
├── security.py          # verificación de API key
├── repositories/        # acceso a Stored Procedures (sin reglas de negocio)
├── services/            # reglas de negocio y flujos
├── schemas/             # modelos Pydantic de entrada y salida
├── routers/             # endpoints HTTP y WebSocket
└── websocket/manager.py # ConnectionManager: clientes y eventos por vehículo
```

Flujo: router → service → repository → Stored Procedure → Amazon RDS.

## Autenticación

Las operaciones de eliminación y de control de DEMO exigen el header `X-API-Key` con el valor de `API_KEY`. Sin él responden 401; con una clave incorrecta, 403. En Swagger se configura con el botón **Authorize**.

## Endpoints HTTP

Las consultas usan GET; las escrituras, actualizaciones y acciones usan POST.

| Área      | Método y ruta                                                                  | Stored Procedures                                                                      |
| --------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| Vehículos | `GET /vehiculos`                                                               | sp_obtener_vehiculos                                                                   |
| Vehículos | `GET /vehiculos/{id}`                                                          | sp_obtener_vehiculo, sp_obtener_comandos_vehiculo, sp_obtener_estado, sp_obtener_demos |
| Vehículos | `POST /vehiculos`                                                              | sp_crear_vehiculo                                                                      |
| Vehículos | `POST /vehiculos/{id}/actualizar`                                              | sp_actualizar_vehiculo                                                                 |
| Vehículos | `POST /vehiculos/{id}/eliminar` (API key)                                      | sp_eliminar_vehiculo                                                                   |
| Comandos  | `GET /vehiculos/{id}/comandos`                                                 | sp_obtener_comandos_vehiculo                                                           |
| Comandos  | `POST /vehiculos/{id}/comandos`                                                | sp_crear_comando                                                                       |
| Comandos  | `POST /vehiculos/{id}/comandos/{id_comando}/actualizar`                        | sp_actualizar_comando                                                                  |
| Comandos  | `POST /vehiculos/{id}/comandos/{id_comando}/eliminar` (API key)                | sp_eliminar_comando                                                                    |
| Estado    | `GET /vehiculos/{id}/estado`                                                   | sp_obtener_estado                                                                      |
| Estado    | `POST /vehiculos/{id}/movimientos`                                             | sp_actualizar_estado, sp_registrar_historial                                           |
| Historial | `GET /vehiculos/{id}/historial` (máx. 10)                                      | sp_obtener_historial                                                                   |
| DEMO      | `GET /vehiculos/{id}/demos`                                                    | sp_obtener_demos                                                                       |
| DEMO      | `POST /vehiculos/{id}/demos`                                                   | sp_crear_demo                                                                          |
| DEMO      | `POST /vehiculos/{id}/demos/{id_demo}/actualizar`                              | sp_actualizar_demo                                                                     |
| DEMO      | `POST /vehiculos/{id}/demos/{id_demo}/eliminar` (API key)                      | sp_eliminar_demo                                                                       |
| DEMO      | `GET /vehiculos/{id}/demos/{id_demo}/movimientos`                              | sp_obtener_movimientos_demo                                                            |
| DEMO      | `POST /vehiculos/{id}/demos/{id_demo}/movimientos`                             | sp_agregar_movimiento_demo                                                             |
| DEMO      | `POST /vehiculos/{id}/demos/{id_demo}/movimientos/{id_mov}/actualizar`         | sp_actualizar_movimiento_demo                                                          |
| DEMO      | `POST /vehiculos/{id}/demos/{id_demo}/movimientos/{id_mov}/eliminar` (API key) | sp_eliminar_movimiento_demo                                                            |
| DEMO      | `POST /vehiculos/{id}/demos/{id_demo}/iniciar` (API key)                       | sp_obtener_movimientos_demo, sp_actualizar_estado                                      |
| DEMO      | `POST /vehiculos/{id}/demos/cancelar` (API key)                                | (cancela la tarea en ejecución)                                                        |

## Reglas de negocio

- **Movimiento individual:** valida que el vehículo y el comando existan, estén activos y que el comando pertenezca al vehículo. Actualiza el estado y registra el historial en **una misma transacción**; solo después del `commit` notifica por WebSocket.
- **DEMO:** los movimientos se leen de RDS, se emiten por WebSocket respetando `duracion_ms` y `pausa_ms`, y actualizan el estado. **Nunca se registran en el historial.**
- **Historial:** el GET devuelve como máximo los 10 movimientos individuales más recientes; RDS conserva el historial completo.
- Solo puede haber una DEMO en ejecución por vehículo (409 si se intenta otra).
- `conectado` conserva su valor previo; recibir una solicitud HTTP no lo vuelve verdadero.

## WebSocket

URL: `ws://localhost:8000/ws/vehiculos/{id_vehiculo}`

Cada cliente solo recibe los eventos del vehículo que monitorea; puede haber varios clientes por vehículo. Todos los mensajes comparten estos campos: `evento`, `id_vehiculo`, `comando`, `codigo` y `timestamp` (UTC, ISO 8601); según el evento se agregan otros.

| Evento            | Cuándo se emite                                              | Campos adicionales                            |
| ----------------- | ------------------------------------------------------------ | --------------------------------------------- |
| `estado_actual`   | Al abrir la conexión                                         | `conectado`                                   |
| `movimiento`      | Tras registrar un movimiento individual                      | `origen`                                      |
| `demo_inicio`     | Al comenzar una DEMO                                         | `id_demo`, `total_movimientos`                |
| `demo_movimiento` | Por cada movimiento de la DEMO                               | `id_demo`, `orden`, `duracion_ms`, `pausa_ms` |
| `demo_fin`        | Al terminar una DEMO                                         | `id_demo`                                     |
| `demo_cancelada`  | Al cancelar una DEMO                                         | `id_demo`                                     |
| `demo_error`      | Si falla la DEMO                                             | `id_demo`, `mensaje`                          |
| `error`           | Vehículo inexistente (la conexión se cierra con código 4404) | `mensaje`                                     |

Ejemplo:

```json
{
  "evento": "demo_movimiento",
  "id_vehiculo": 1,
  "comando": "AVANZAR",
  "codigo": 1,
  "timestamp": "2026-10-15T05:40:12.123456+00:00",
  "id_demo": 1,
  "orden": 1,
  "duracion_ms": 2000,
  "pausa_ms": 400
}
```

Enviar un mensaje por WebSocket no confirma la ejecución física: la integración con el microcontrolador (ESP8266/ESP32) corresponde a una práctica posterior.

## Seguridad

- Credenciales solo en variables de entorno; `.env` está excluido por `.gitignore`.
- Parámetros enlazados en todas las llamadas a Stored Procedures (sin concatenar SQL).
- Los errores de base de datos se registran en el servidor y al cliente solo se le devuelve un mensaje genérico.
