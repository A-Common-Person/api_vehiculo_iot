-- Ejecutar después de V001, con un cliente que detenga el script al primer error.
-- Si difiere el inventario observado, el CHECK falla antes de crear datos.

CREATE TEMPORARY TABLE validar_inventario_43 (
    coincide INT NOT NULL CHECK (coincide = 1)
) ENGINE=InnoDB;

START TRANSACTION;

INSERT INTO validar_inventario_43 (coincide)
SELECT (
    (SELECT COUNT(*) FROM vehiculos) = 2
    AND EXISTS (
        SELECT 1 FROM vehiculos
        WHERE id_vehiculo = 1 AND nombre = 'Excavadora IoT'
          AND modelo = 'Modelo X' AND microcontrolador = 'ESP8266' AND activo = 1
    )
    AND EXISTS (
        SELECT 1 FROM vehiculos WHERE id_vehiculo = 3 AND nombre = 'Arduino' AND modelo = 'Uno'
    )
    AND (
        SELECT COUNT(*) FROM comandos WHERE id_vehiculo = 1 AND activo = 1
    ) = 13
    AND (
        SELECT COUNT(*) FROM comandos
        WHERE id_vehiculo = 1 AND activo = 1 AND codigo IN (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15)
    ) = 13
);

INSERT INTO modelos_vehiculo (nombre) VALUES ('Modelo X');
SET @id_modelo_x = LAST_INSERT_ID();

INSERT INTO capacidades_modelo (id_modelo, codigo)
SELECT @id_modelo_x, codigo
FROM comandos
WHERE id_vehiculo = 1 AND activo = 1
ORDER BY codigo;

INSERT INTO inventario_unidades (id_vehiculo, id_modelo, estado_comercial)
VALUES (1, @id_modelo_x, 'disponible'), (3, NULL, 'inactivo');

COMMIT;
DROP TEMPORARY TABLE validar_inventario_43;
