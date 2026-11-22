-- Ejecutar después de V002. Resultados esperados en un esquema recién migrado.

SELECT v.id_vehiculo, v.nombre, m.nombre AS modelo_comercial, i.estado_comercial,
       COUNT(c.codigo) AS capacidades_modelo
FROM inventario_unidades i
JOIN vehiculos v ON v.id_vehiculo = i.id_vehiculo
LEFT JOIN modelos_vehiculo m ON m.id_modelo = i.id_modelo
LEFT JOIN capacidades_modelo c ON c.id_modelo = i.id_modelo
GROUP BY v.id_vehiculo, v.nombre, m.nombre, i.estado_comercial
ORDER BY v.id_vehiculo;

-- Esperado: cero capacidades habilitadas para invitados en la carga inicial.
SELECT COUNT(*) AS capacidades_invitado
FROM capacidades_modelo
WHERE permite_invitado = TRUE;

-- Esperado: cero vehículos sin metadatos de inventario tras la migración.
SELECT v.id_vehiculo AS vehiculo_sin_inventario
FROM vehiculos v
LEFT JOIN inventario_unidades i ON i.id_vehiculo = v.id_vehiculo
WHERE i.id_vehiculo IS NULL;
