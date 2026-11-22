-- Guardar los resultados antes y después del ensayo, sin operaciones concurrentes.

SELECT DATABASE() AS esquema, VERSION() AS version_mysql;

SELECT 'vehiculos' AS tabla, COUNT(*) AS filas FROM vehiculos
UNION ALL SELECT 'comandos', COUNT(*) FROM comandos
UNION ALL SELECT 'estado_vehiculo', COUNT(*) FROM estado_vehiculo
UNION ALL SELECT 'historial_comandos', COUNT(*) FROM historial_comandos
UNION ALL SELECT 'demos', COUNT(*) FROM demos
UNION ALL SELECT 'demo_movimientos', COUNT(*) FROM demo_movimientos;

SELECT id_vehiculo, nombre, modelo, microcontrolador, activo
FROM vehiculos
ORDER BY id_vehiculo;

SELECT routine_name
FROM information_schema.routines
WHERE routine_schema = DATABASE() AND routine_type = 'PROCEDURE'
ORDER BY routine_name;

CALL sp_obtener_vehiculo(1);
CALL sp_obtener_comandos_vehiculo(1);
CALL sp_obtener_estado(1);
CALL sp_obtener_demos(1);
-- FastAPI ya devuelve como máximo diez movimientos individuales.
SELECT h.id_historial, h.id_vehiculo, c.nombre AS comando, c.codigo, h.fecha_hora, h.origen
FROM historial_comandos h
LEFT JOIN comandos c ON c.id_comando = h.id_comando
WHERE h.id_vehiculo = 1
ORDER BY h.fecha_hora DESC, h.id_historial DESC
LIMIT 10;
