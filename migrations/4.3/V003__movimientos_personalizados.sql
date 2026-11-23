-- Ejecutar sobre el esquema del proyecto, primero en una copia respaldada.
CREATE TABLE IF NOT EXISTS movimientos_personalizados (
    id_movimiento INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    id_vehiculo INT NOT NULL,
    id_usuario BIGINT UNSIGNED NULL,
    nombre VARCHAR(80) NOT NULL,
    id_comando INT NOT NULL,
    duracion_ms INT UNSIGNED NOT NULL,
    pausa_ms INT UNSIGNED NOT NULL DEFAULT 0,
    eliminado BOOLEAN NOT NULL DEFAULT FALSE,
    id_demo_origen INT NULL UNIQUE,
    INDEX ix_movimientos_editor (id_vehiculo, id_usuario, eliminado),
    FOREIGN KEY (id_vehiculo) REFERENCES vehiculos(id_vehiculo),
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_comando) REFERENCES comandos(id_comando),
    CHECK (duracion_ms BETWEEN 100 AND 3000 AND pausa_ms <= 3000)
) ENGINE=InnoDB;

SET @ddl_nombre_paso = IF(EXISTS (
    SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE()
    AND table_name = 'demo_movimientos' AND column_name = 'nombre_movimiento'
), 'SELECT 1', 'ALTER TABLE demo_movimientos ADD COLUMN nombre_movimiento VARCHAR(80) NULL');
PREPARE agregar_nombre_paso FROM @ddl_nombre_paso;
EXECUTE agregar_nombre_paso;
DEALLOCATE PREPARE agregar_nombre_paso;

-- Importa únicamente los movimientos creados con el antiguo formulario.
-- Las demos ordinarias de un paso siguen siendo demos.
INSERT INTO movimientos_personalizados
    (id_vehiculo, id_usuario, nombre, id_comando, duracion_ms, pausa_ms, id_demo_origen)
SELECT d.id_vehiculo, p.id_usuario, d.nombre, s.id_comando, s.duracion_ms, s.pausa_ms, d.id_demo
FROM demos d
JOIN demo_movimientos s ON s.id_demo = d.id_demo
LEFT JOIN propiedad_demo p ON p.id_demo = d.id_demo
WHERE d.activo = FALSE
  AND d.descripcion = 'Movimiento reutilizable. Solo se usa como paso de otra demo.'
  AND NOT EXISTS (SELECT 1 FROM movimientos_personalizados m WHERE m.id_demo_origen = d.id_demo)
  AND (SELECT COUNT(*) FROM demo_movimientos t WHERE t.id_demo = d.id_demo) = 1
  AND s.duracion_ms BETWEEN 100 AND 3000 AND s.pausa_ms <= 3000;
