# Validación de Administración IoT 4.3

## Resultados del ensayo

La matriz resume las pruebas en la copia de RDS o en MySQL local aislado. Las
pruebas de integración usan un ESP8266 simulado cuando se indica. Las pruebas
físicas son las confirmadas por el usuario con la Excavadora IoT.

| Caso | Prueba | Resultado en el ensayo |
| --- | --- | --- |
| P01 | Acceso de Administrador | Correcto. La cuenta abre Administración y las credenciales inválidas se rechazan. |
| P02 | Alta de unidad | Correcto. Se probó el alta, la edición y la baja lógica de una unidad. |
| P03 | Alta de cliente | Correcto. Se registró un comprador desde el navegador. |
| P04 | Asignación | Correcto. El comprador recibe la unidad y el acceso se revoca al liberarla. |
| P05 | Aislamiento de comprador | Correcto. FastAPI rechaza consultas y suscripciones por unidad ajena. |
| P06 | Control | Correcto. El usuario confirmó el joystick, las órdenes del brazo y los botones en el carrito. |
| P07 | WebSocket | Correcto. El canal autorizado recibe eventos de la unidad y el ESP8266 confirma las órdenes. |
| P08 | Diez movimientos individuales | Correcto. Monitoreo mostró los últimos diez registros del comprador. Las demos y las pruebas de exhibición conservan el historial individual. |
| P09 | Persistencia de demos | Correcto. Se guardaron demos de empresa y privadas. Se verificó el orden de pasos y se rechazó la edición ajena. |
| P10 | Ejecución y cancelación de demo | Correcto. El usuario confirmó la ejecución física. La prueba de integración verificó la prioridad de DETENER y la cancelación. |
| P11 | Prueba de Invitado | Correcto. Se verificaron el contador, los mandos configurados y la caducidad. El usuario probó los mandos en el carrito. |
| P12 | Rechazo de Administración a Invitado | Correcto. El token de exhibición recibe 401 en las rutas administrativas. |
| P13 | Rechazo de vehículo ajeno | Correcto. El comprador recibe 403 y el invitado carece de acceso a las rutas privadas. |
| P14 | Exclusividad | Correcto. Dos navegadores disputaron la misma unidad simulada. Sólo el primero obtuvo la reserva. |
| P15 | Reconexión | Correcto. Se verificó el reinicio de FastAPI con el mismo certificado y la misma credencial. El usuario confirmó la reconexión física. |
| P16 | Diseño adaptable | Correcto. Se probaron las vistas y el editor en navegador con un ancho de 390 px. |
| P17 | Auditoría | Correcto. Se verificaron los registros de alta, asignación, cambios de demos e inicio y cierre de exhibición. |

## Recorrido para repetir las pruebas

1. En el ensayo con la copia de RDS, inicia sesión como Administrador, registra
   un comprador y asigna la unidad a su cuenta. Revisa el evento de auditoría.
2. Con el comprador, prueba Control y los diez últimos movimientos. Guarda una
   demo, reábrela y verifica el orden de pasos. Ejecútala y cancélala con DETENER.
3. En una sesión distinta, intenta consultar la misma unidad sin asignación.
   Comprueba que la API y el WebSocket rechazan el acceso.
4. En Administración, libera la unidad, cámbiala a **En exhibición** y habilita
   sus mandos de Invitado. Desde dos navegadores intenta reservarla al mismo
   tiempo. Verifica la exclusividad, DETENER y la liberación al agotar los 45 s.
5. Con el carrito detenido, reinicia FastAPI conservando la configuración del
   dispositivo y comprueba el nuevo enlace. Reabre Monitoreo y revisa los
   indicadores de API, RDS y WebSocket por separado.

## Validación pública pendiente

La aplicación 4.3 se ensayó en la vista local. En el despliegue, el frontend de
GitHub Pages debe abrir Administración 4.3 y usar HTTPS y WSS del backend en
EC2. La integración del dispositivo también debe comprobarse con el destino y
certificado de esa publicación. Ejecuta las [migraciones](../migrations/4.3/README.md)
sobre la base autorizada con respaldo y repite el recorrido desde la URL
pública. Registra los resultados de los tres roles y comprueba el sitio, el
repositorio y Swagger antes de la entrega.
