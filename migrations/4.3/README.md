# Migraciones de Administración IoT 4.3

El esquema original tiene seis tablas y 21 procedimientos. `V001` incorpora
once tablas de administración sin modificar las tablas ni los procedimientos
originales. `V002` incorpora al inventario la Excavadora IoT y la unidad Arduino
de prueba. La carga registra las capacidades activas del modelo y deja por
configurar los mandos de Invitado. El identificador de cada unidad sigue siendo
`vehiculos.id_vehiculo`.

El [diagrama de relaciones](diagrama_er.mmd) muestra las tablas existentes y las
relaciones de modelos, asignaciones, demos privadas y reservas de control.

## Orden de ejecución

1. Toma una instantánea de RDS y verifica el estado **Disponible**. Usa una copia
   aislada para el ensayo con los datos y privilegios que tendrá el despliegue.
2. Selecciona el esquema de destino y ejecuta
   [comprobar_estructura_original.sql](comprobar_estructura_original.sql) para
   registrar los conteos iniciales, los procedimientos y el estado e historial.
3. Ejecuta [V001](V001__esquema_administracion.sql) una sola vez por esquema. Si
   falla alguna sentencia, inspecciona el esquema antes de reintentar. MySQL
   puede confirmar cada sentencia DDL de manera implícita.
4. Ejecuta [V002](V002__inventario_inicial.sql) con un cliente por lotes que se
   detenga ante el primer error. La carga exige las unidades 1 y 3 y los 13
   comandos activos previstos para la Excavadora IoT. Si la validación falla
   en un cliente que mantiene abierta la sesión, ejecuta `ROLLBACK` allí.
5. Repite las comprobaciones originales y ejecuta
   [comprobar_administracion.sql](comprobar_administracion.sql). Compara los
   conteos y el historial con el paso 2. En la carga inicial la unidad 1 queda
   disponible, la 3 inactiva y los permisos de Invitado quedan sin habilitar.

## Recuperación

El [script de reversión](revertir_solo_ensayo.sql) selecciona explícitamente
`vehiculo_iot_43_prueba` y elimina las tablas administrativas de ese esquema.
Ejecútalo únicamente en el ensayo local con un cliente que se detenga ante el
primer error. Para recuperar una instancia operativa, restaura la instantánea
en una instancia separada y verifica los datos antes de cambiar la conexión
de la aplicación. Revisa las escrituras posteriores a la fecha del respaldo.
