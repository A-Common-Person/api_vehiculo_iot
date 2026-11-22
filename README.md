# API Vehículo IoT (publicada en Amazon EC2)

API en Python con FastAPI y programación orientada a objetos para controlar y monitorear un vehículo IoT (excavadora). Usa los 21 Stored Procedures del esquema `vehiculo_iot` alojado en Amazon RDS y transmite eventos en tiempo real por WebSocket. Está **publicada en Amazon EC2 con HTTPS/WSS** y también puede ejecutarse en `localhost:8000` para desarrollo.

## URLs públicas

- Swagger UI (HTTPS): https://vehiculo-iot-erik.duckdns.org/docs
- Salud: https://vehiculo-iot-erik.duckdns.org/health
- WebSocket (WSS): `wss://vehiculo-iot-erik.duckdns.org/ws/vehiculos/{id_vehiculo}`
- Repositorio: https://github.com/A-Common-Person/api_vehiculo_iot

## Requisitos

- Python 3.11 o superior
- Una instancia de Amazon RDS (MySQL) con la base `vehiculo_iot` y sus 21 Stored Procedures
- Security Group de RDS con MySQL TCP 3306: en producción **solo desde el Security Group de la EC2**; para desarrollo local, restringido a tu IP

## Instalación y ejecución local

```powershell
git clone https://github.com/A-Common-Person/api_vehiculo_iot
cd api_vehiculo_iot
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

## Ensayo local de Administración 4.3

El catálogo se consulta y modifica en `/administracion/modelos` y
`/administracion/modelos/{id_modelo}`. El inventario se consulta en
`/administracion/inventario`. Las altas y ediciones de unidades se hacen en
`/administracion/unidades` y `/administracion/unidades/{id_vehiculo}`.
Estas rutas requieren una sesión de Administrador.

Para dar de baja una unidad, envía `estado_comercial: "inactivo"` en su edición.
Se conservan el ID, los movimientos y las asignaciones anteriores. Una unidad
asignada debe liberarse antes de cambiar de modelo o estado, y una reserva de
control abierta bloquea la edición. Los modelos se desactivan sólo cuando sus
unidades están inactivas. Las modificaciones quedan en auditoría y reutilizan
el esquema y los procedimientos ya existentes.

`GET /administracion/capacidades` enumera los códigos registrados en el sistema.
`PUT /administracion/modelos/{id_modelo}/capacidades` guarda los códigos
habilitados del modelo. Las consultas autenticadas y el control usan la
intersección de esas capacidades con los comandos activos de cada unidad.
DETENER sigue disponible si el comando está activo en el vehículo. Las reservas
abiertas bloquean cambios de capacidades del modelo hasta que termine el control.

Después de aplicar V001 y V002 en la copia de RDS, abre PowerShell
en la carpeta del backend. El siguiente comando crea una cuenta
administrativa de prueba y arranca Swagger en el puerto 8001.

```powershell
.\scripts\probar_administracion.ps1 -CrearCuenta administrador
```

El script pide el endpoint de la copia, las credenciales de MySQL y
los datos de la cuenta nueva. Valida el certificado y el nombre de
RDS con la CA de AWS y configura sólo la sesión local de PowerShell.
En arranques siguientes, ejecuta el script sin `-CrearCuenta`. Puedes
usar `-CrearCuenta usuario` para preparar una cuenta de comprador.

Pruebas reproducibles desde Swagger

1. Abre [Swagger local](http://127.0.0.1:8001/docs) y comprueba que
   `GET /health` reporte `database: ok`.
2. Ejecuta `POST /auth/login` con el correo y la contraseña de la cuenta
   de la aplicación. Usa solamente el valor de `access_token` en **Authorize**.
3. Consulta `GET /auth/me` y `GET /administracion/inventario` con la cuenta
   administrativa. En una copia recién migrada se muestran las unidades
   1 y 3 con los estados cargados por V002.
4. Una cuenta de comprador recibe 403 al consultar el inventario. En
   `GET /vehiculos/mios` ve únicamente sus unidades asignadas, por lo que
   recibe una lista vacía si es nueva.
5. Ejecuta `POST /auth/logout`. Una consulta posterior con el mismo token
   debe recibir 401.

### Clientes y asignaciones

Con la cuenta administrativa en **Authorize**, abre
`GET /administracion/clientes` para ver las cuentas de comprador.
Si hace falta una, `POST /administracion/clientes` recibe `nombre`,
`correo` y una `password` de al menos 12 caracteres. El rol se asigna
en el servidor.

Para asignar la unidad 1, ejecuta
`PUT /administracion/unidades/1/asignacion` con el `id_usuario` del
comprador. Para reasignar, envía el nuevo `id_usuario` y, en
`id_asignacion_esperada`, el ID vigente que muestra el inventario.
Si alguien lo cambió entre tanto, la API responde 409. Repetir la
asignación vigente al mismo comprador devuelve la fila existente.

Para liberar la unidad, ejecuta
`DELETE /administracion/unidades/1/asignacion` e indica como parámetro
`id_asignacion_esperada`. Tanto la reasignación como la liberación
conservan el historial comercial. Cada cambio queda en
`GET /administracion/auditoria` y las asignaciones se consultan en
`GET /administracion/unidades/1/asignaciones`.

Prueba con el token de un comprador antes y después de reasignar.
`GET /vehiculos/mios` pierde la unidad cuando termina su asignación,
y una consulta directa a su estado devuelve 403. Una reserva de
control abierta impide cambios de asignación hasta que concluya.

### WebSocket autenticado en el ensayo

Con FastAPI local ejecutándose, abre otra terminal en el backend y
ejecuta este cliente de prueba.

```powershell
.\.venv\Scripts\python.exe .\scripts\probar_websocket.py
```

Usa el correo y la contraseña del comprador que tiene la Excavadora
asignada y elige la unidad 1. Debe llegar un evento `estado_actual`.
Una conexión con el mismo comprador a la unidad 3 debe cerrar con
4403. Si dejas conectada la sesión autorizada y liberas o reasignas la
unidad desde Swagger como Administrador, ese canal también se cierra
con 4403. El cliente finaliza su propia sesión al salir.

El cliente web deberá abrir `/ws/vehiculos/{id_vehiculo}` sin poner el
token en la URL. Su primer mensaje JSON tendrá `tipo` igual a
`autenticar` y el token de sesión en `token`. La autorización se
revisa antes de entregar eventos y periódicamente si el canal está
inactivo. El cierre de sesión revoca sus conexiones, con código 4401.
Los demás mensajes de aplicación se envían desde el servidor.

### Prueba local con el ESP8266

Conecta la computadora y el ESP8266 a la misma red Wi-Fi. Consulta la IPv4 de
la computadora con `ipconfig` y reemplaza `192.168.1.50` por esa dirección.
Detén el backend de pruebas si sigue ejecutándose y arráncalo con:

```powershell
.\scripts\probar_administracion.ps1 -IPRedLocal 192.168.1.50 -PrepararDispositivo
```

El script usa la copia de RDS y crea `IoT43Local.h` junto a `Carrito_WS.ino`.
El archivo contiene la credencial de la unidad 1 y la huella del certificado
local. Guárdalo en tu equipo y exclúyelo de Git. Carga el sketch actualizado
en el NodeMCU ESP8266. En arranques posteriores usa `-IPRedLocal` con la misma
IPv4. Repite la preparación y la carga del sketch si cambia la IP o vence
el certificado. La preparación reemplaza la credencial anterior.

Swagger y el navegador siguen usando `127.0.0.1:8001`. En la red local, el
ESP8266 se conecta a `wss://<IPv4>:8443/ws/dispositivos/1`. Si Windows
Firewall bloquea la conexión, permite TCP 8443 para la red privada, con
alcance limitado a la red local.

La terminal de FastAPI muestra `ESP8266 unidad 1: listo y autenticado` cuando
termina la conexión. Si RDS falla durante una comprobación, FastAPI pausa el
control, mantiene el WebSocket y vuelve a comprobar la credencial. La terminal
muestra el motivo del cierre si el canal termina.

Con una cuenta compradora que tenga asignada la unidad 1, abre **Control**.
Cada cambio de dirección en los joysticks envía un pulso de 250 ms. El sketch
anuncia los códigos que admite al conectarse. FastAPI combina esa lista con
los comandos activos del vehículo y las capacidades del modelo. Los sketches
4.3 anteriores siguen aceptando Avanzar y DETENER. Carga el sketch actualizado
para habilitar los demás mandos con la credencial local que ya tienes.

`POST /vehiculos/{id}/control/orden` envía un código autorizado y requiere el
identificador del enlace devuelto por `GET /vehiculos/{id}/control/prueba`.
**DETENER** tiene prioridad y puede cancelar una orden pendiente del mismo
comprador. El ESP8266 apaga sus salidas antes de confirmar el pulso y FastAPI
registra las confirmaciones en el historial con origen `CONTROL_4_3`. La
confirmación verifica la salida del ESP8266. El desplazamiento se comprueba
físicamente. La DEMO integrada queda fuera de los mandos por pulso.

El modo compatible de Control y Monitoreo usa sus rutas existentes con
`ADMINISTRACION_HABILITADA=false`.

## Configuración (`.env`)

| Variable      | Descripción                                                 |
| ------------- | ----------------------------------------------------------- |
| `DB_HOST`     | Endpoint de Amazon RDS                                      |
| `DB_PORT`     | Puerto MySQL (3306)                                         |
| `DB_USER`     | Usuario de MySQL (preferentemente solo con permiso EXECUTE) |
| `DB_PASSWORD` | Contraseña del usuario                                      |
| `DB_NAME`     | Nombre del esquema (`vehiculo_iot`)                         |
| `API_KEY`     | Clave para las operaciones de eliminación y control de DEMO |
| `ADMINISTRACION_HABILITADA` | Activa el entorno local de Administración. Por defecto es `false`. |
| `DB_SSL_CA`   | Archivo PEM de la CA de RDS. Obligatorio para Administración. |

El archivo `.env` no se versiona; el repositorio incluye `.env.example` solo con valores de ejemplo.

## Arquitectura

### Despliegue en AWS

```
Cliente externo (Postmate / Swagger / navegador)
        │  HTTPS (443) / WSS (443)
        ▼
Caddy: proxy inverso + certificado Let's Encrypt        ┐
        │  HTTP / WS (127.0.0.1:8000)                   │ Amazon EC2
        ▼                                               │ (Windows Server)
FastAPI + Uvicorn (servicio de Windows con NSSM)        ┘
        │  Stored Procedures (MySQL, 3306)
        ▼
Amazon RDS for MySQL: base vehiculo_iot
```

La API escucha únicamente en `127.0.0.1:8000`; solo Caddy es accesible desde Internet (puertos 80 y 443). API y Caddy son servicios de Windows con arranque automático, por lo que siguen operando al cerrar VS Code o la sesión de escritorio remoto.

### Organización del código (POO)

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

## Despliegue en Amazon EC2 (Windows Server)

1. **Security Group de EC2:** 3389 (RDP) solo desde la IP del administrador; 80 y 443 públicos. El puerto 8000 permanece cerrado.
2. **Security Group de RDS:** 3306 permitido únicamente desde el Security Group de la EC2.
3. **Elastic IP** asociada a la instancia y dominio DuckDNS apuntando a ella.
4. **Firewall de Windows:** reglas de entrada para los puertos 80 y 443.
5. Instalar Python y Git, clonar el repositorio en `C:\api`, crear el entorno virtual e instalar `requirements.txt`.
6. Crear manualmente `C:\api\.env` en el servidor con los datos de RDS y la API key.
7. **Servicio de la API (NSSM):**

```powershell
nssm install ApiVehiculo "C:\api\venv\Scripts\python.exe" "-m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers"
nssm set ApiVehiculo AppDirectory C:\api
nssm set ApiVehiculo Start SERVICE_AUTO_START
nssm start ApiVehiculo
```

8. **Caddy** como proxy inverso con certificado automático de Let's Encrypt. `C:\caddy\Caddyfile`:

```
vehiculo-iot-erik.duckdns.org {
    reverse_proxy 127.0.0.1:8000
}
```

Caddy también se ejecuta como servicio con NSSM y reenvía las conexiones WebSocket sin configuración adicional.

Para actualizar el servidor tras un cambio en GitHub: `git pull` en `C:\api` y `nssm restart ApiVehiculo`.

## Autenticación

Las operaciones de eliminación y de control de DEMO exigen el header `X-API-Key` con el valor de `API_KEY`. Sin él responden 401; con una clave incorrecta, 403. En Swagger se configura con el botón **Authorize**.

## Endpoints HTTP

Las consultas usan GET; las escrituras, actualizaciones y acciones usan POST.

| Área      | Método y ruta                                                                  | Stored Procedures                                                                      |
| --------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| Salud     | `GET /health`                                                                  | (ninguno)                                                                              |
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

Cuerpo del movimiento individual (`POST /vehiculos/{id}/movimientos`):

```json
{ "id_comando": 2 }
```

Los esquemas completos de cuerpo y respuesta de cada endpoint están en Swagger UI.

## Reglas de negocio

- **Movimiento individual:** valida que el vehículo y el comando existan, estén activos y que el comando pertenezca al vehículo. Actualiza el estado y registra el historial en **una misma transacción**; solo después del `commit` notifica por WebSocket.
- **DEMO:** los movimientos se leen de RDS, se emiten por WebSocket respetando `duracion_ms` y `pausa_ms`, y actualizan el estado. **Nunca se registran en el historial.**
- **Historial:** el GET devuelve como máximo los 10 movimientos individuales más recientes, del más reciente al más antiguo; RDS conserva el historial completo.
- Solo puede haber una DEMO en ejecución por vehículo (409 si se intenta otra).
- `conectado` conserva su valor previo; recibir una solicitud HTTP no lo vuelve verdadero.

## WebSocket

- Público: `wss://vehiculo-iot-erik.duckdns.org/ws/vehiculos/{id_vehiculo}`
- Local: `ws://localhost:8000/ws/vehiculos/{id_vehiculo}`

Cada cliente solo recibe los eventos del vehículo que monitorea; puede haber varios clientes por vehículo. Al conectar, el servidor envía de inmediato el último estado guardado en RDS. Todos los mensajes comparten estos campos: `evento`, `id_vehiculo`, `comando`, `codigo` y `timestamp` (UTC, ISO 8601); según el evento se agregan otros.

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

Tras una desconexión, el cliente puede volver a conectarse y recibe de nuevo el último estado.

### Movimientos individuales vs. DEMO

|                     | Movimiento individual                             | DEMO                                            |
| ------------------- | ------------------------------------------------- | ----------------------------------------------- |
| Inicio              | `POST /vehiculos/{id}/movimientos`                | `POST /vehiculos/{id}/demos/{id_demo}/iniciar`  |
| Estado del vehículo | Se actualiza                                      | Se actualiza en cada paso                       |
| Historial           | **Se registra** (misma transacción que el estado) | **No se registra**                              |
| Notificación WSS    | Un evento `movimiento`                            | `demo_inicio`, N `demo_movimiento` y `demo_fin` |
| Simultaneidad       | —                                                 | Una sola DEMO por vehículo (409)                |
| Cancelación         | —                                                 | Posible con la API key                          |

Enviar un mensaje por WebSocket no confirma la ejecución física: estos eventos son el futuro canal de instrucciones hacia el microcontrolador (ESP8266/ESP32). En esta etapa no se exige conexión física ni confirmación de motores.

## Seguridad

- Credenciales solo en variables de entorno; `.env` está excluido por `.gitignore`.
- Parámetros enlazados en todas las llamadas a Stored Procedures (sin concatenar SQL).
- Los errores de base de datos se registran en el servidor y al cliente solo se le devuelve un mensaje genérico.
- RDS solo acepta conexiones desde la instancia EC2 (Security Group); el escritorio remoto (3389) está limitado a la IP del administrador.
- La API solo escucha en localhost; todo el tráfico externo pasa por HTTPS/WSS a través de Caddy.
- Las operaciones de eliminación y control de DEMO requieren `X-API-Key`.

## Pruebas funcionales en el entorno público

1. **POST + WSS:** dos clientes WSS conectados al vehículo 1 reciben `estado_actual`; un POST de movimiento genera un evento `movimiento` en ambos, el estado cambia y el movimiento queda en el historial.
2. **GET historial:** devuelve como máximo 10 movimientos individuales, del más reciente al más antiguo, sin movimientos de DEMO.
3. **DEMO por WSS:** con el WSS abierto, el POST de iniciar la DEMO transmite `demo_inicio`, los 8 `demo_movimiento` temporizados y `demo_fin`; el último estado queda en `DETENER` y el historial no cambia.
