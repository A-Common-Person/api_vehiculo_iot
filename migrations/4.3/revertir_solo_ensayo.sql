-- Reversión solamente del esquema local de ensayo, nunca contra vehiculo_iot.
-- Borra las tablas nuevas y sus filas. Conserva las seis tablas y los SP originales.
-- Cada DROP es un DDL independiente. No activar --force ni deshabilitar claves foráneas.
USE vehiculo_iot_43_prueba;

DROP TABLE IF EXISTS auditoria_administracion;
DROP TABLE IF EXISTS credenciales_dispositivo;
DROP TABLE IF EXISTS reservas_control;
DROP TABLE IF EXISTS propiedad_demo;
DROP TABLE IF EXISTS autorizaciones_soporte;
DROP TABLE IF EXISTS asignaciones_vehiculo;
DROP TABLE IF EXISTS inventario_unidades;
DROP TABLE IF EXISTS capacidades_modelo;
DROP TABLE IF EXISTS modelos_vehiculo;
DROP TABLE IF EXISTS sesiones_usuario;
DROP TABLE IF EXISTS usuarios;
