# Publicación de Administración IoT 4.3

## FastAPI y RDS

1. Verifica la migración de esta rama sobre el RDS de ensayo siguiendo la [matriz 4.3](validacion-4.3.md). Para publicar sobre otra instancia, identifica el destino, toma una instantánea de ese RDS y revisa la migración antes de aplicarla.
2. En el `.env` de la API configura `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` y `DB_NAME` para la base migrada. Usa el endpoint DNS de RDS. Configura `DB_SSL_CA` con el [bundle regional de RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html).
3. Activa `ADMINISTRACION_HABILITADA=true` y `PUBLICACION_HABILITADA=true` en ese mismo `.env`.
4. En EC2, el servicio de FastAPI debe escuchar por loopback. Mantén el `reverse_proxy 127.0.0.1:8000` de Caddy y deja en NSSM estos argumentos de Uvicorn.

   ```powershell
   -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
   ```

   Caddy termina TLS para `vehiculo-iot-erik.duckdns.org` e indica a Uvicorn el esquema externo de HTTPS o WSS. Si habilitas el modo de publicación, la API exige ese esquema. Usa [el proxy inverso de Caddy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy) para ambos protocolos.

5. Desde la carpeta de la API en EC2, crea la cuenta administradora solo si falta en la base de destino. La terminal solicita la contraseña de forma interactiva.

   ```powershell
   python -m app.crear_usuario --rol administrador --publico
   ```

## ESP8266

Usa la carpeta `firmware/Carrito_WS` de este repositorio. El ESP8266 debe poder resolver el dominio y sincronizar su hora por NTP para verificar la vigencia del certificado público.

Desde el entorno de FastAPI configurado para publicar, genera el encabezado de la unidad con la CA raíz que corresponda a la cadena del servidor. Si Caddy sirve una cadena de Let's Encrypt que encadena a ISRG Root X1, descarga el [PEM oficial de ISRG Root X1](https://letsencrypt.org/certs/isrgrootx1.pem). Este certificado se usa en el ESP8266. El `.env` de FastAPI usa la CA de RDS.

```powershell
python -m app.preparar_dispositivo_publico --unidad 1 --ca 'C:\certificados\isrgrootx1.pem' --salida 'C:\ruta\privada\IoT43Publico.h'
```

El comando valida la cadena TLS por el puerto 443 antes de emitir la credencial. La nueva credencial sustituye a la anterior para esa unidad en la base seleccionada. Emítela en una pausa de operación, con el vehículo detenido y sin una reserva de control abierta. Conserva `IoT43Publico.h` en privado. Copia el encabezado al lado de `Carrito_WS.ino` en la carpeta del sketch que vas a cargar. La compilación acepta un solo perfil por carpeta. Para volver al ensayo local usa una copia del sketch con su `IoT43Local.h` correspondiente.

Al iniciar, busca `Conexión confirmada por FastAPI` en el Monitor Serie. En la primera conexión Wi-Fi, el ESP8266 muestra por Serial el nombre y la contraseña temporal de su portal de configuración. El canal del dispositivo es `/ws/dispositivos/1` y manda la credencial en `Authorization`.

## Verificación antes de integrar a `main`

1. Comprueba `/health` y `/openapi.json` por HTTPS. Verifica que aparecen `/auth/login` y `/exhibicion/catalogo`.
2. Si la clave de operador que antes aparecía en el JavaScript público sigue vigente, retírala o rótala en los sistemas que todavía la acepten. El perfil de publicación usa sesiones de usuario y una credencial independiente para el ESP8266.
3. En la vista publicada, entra como administrador, revisa el inventario e inicia sesión como comprador para verificar su unidad asignada. Comprueba que el historial se actualiza y que el mando se detiene al soltarlo.
4. Abre la exhibición como invitado, prueba un movimiento autorizado de dos segundos y comprueba que la unidad se detiene. Reinicia FastAPI durante una ventana de prueba con el carrito detenido y confirma que el ESP8266 se vuelve a enlazar automáticamente.

El origen incluido en CORS para la publicación es `https://a-common-person.github.io`. La API usa la sesión o la credencial de dispositivo para autorizar las operaciones según el canal.
