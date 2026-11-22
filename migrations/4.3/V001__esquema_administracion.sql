-- Etapa 4.3. Seleccionar previamente el esquema de ensayo.
-- Conserva las tablas y los procedimientos de Control y Monitoreo.
-- Cada CREATE TABLE es DDL independiente y puede producir commit implícito.

CREATE TABLE usuarios (
    id_usuario BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    correo VARCHAR(254) NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    password_hash VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    rol ENUM('administrador', 'usuario') NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_usuarios_correo (correo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE sesiones_usuario (
    id_sesion BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_usuario BIGINT UNSIGNED NOT NULL,
    token_hash BINARY(32) NOT NULL,
    creada_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    vence_en DATETIME(6) NOT NULL,
    revocada_en DATETIME(6) NULL,
    UNIQUE KEY uq_sesiones_usuario_token (token_hash),
    KEY ix_sesiones_usuario_vencimiento (id_usuario, vence_en),
    CONSTRAINT fk_sesiones_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario),
    CONSTRAINT ck_sesion_usuario_fechas CHECK (
        vence_en > creada_en AND (revocada_en IS NULL OR revocada_en >= creada_en)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE modelos_vehiculo (
    id_modelo INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL,
    descripcion VARCHAR(255) NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE KEY uq_modelos_nombre (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE capacidades_modelo (
    id_modelo INT NOT NULL,
    codigo INT NOT NULL,
    permite_invitado BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (id_modelo, codigo),
    CONSTRAINT fk_capacidad_modelo FOREIGN KEY (id_modelo) REFERENCES modelos_vehiculo (id_modelo)
) ENGINE=InnoDB;

CREATE TABLE inventario_unidades (
    id_vehiculo INT NOT NULL PRIMARY KEY,
    id_modelo INT NULL,
    estado_comercial ENUM('disponible', 'asignado', 'exhibicion', 'inactivo') NOT NULL,
    KEY ix_inventario_estado_modelo (estado_comercial, id_modelo),
    CONSTRAINT fk_inventario_vehiculo FOREIGN KEY (id_vehiculo) REFERENCES vehiculos (id_vehiculo),
    CONSTRAINT fk_inventario_modelo FOREIGN KEY (id_modelo) REFERENCES modelos_vehiculo (id_modelo),
    CONSTRAINT ck_inventario_modelo CHECK (estado_comercial = 'inactivo' OR id_modelo IS NOT NULL)
) ENGINE=InnoDB;

CREATE TABLE asignaciones_vehiculo (
    id_asignacion BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_vehiculo INT NOT NULL,
    id_usuario BIGINT UNSIGNED NOT NULL,
    inicia_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    finaliza_en DATETIME(6) NULL,
    id_vehiculo_vigente INT GENERATED ALWAYS AS (
        CASE WHEN finaliza_en IS NULL THEN id_vehiculo END
    ) STORED,
    UNIQUE KEY uq_asignacion_unidad_vigente (id_vehiculo_vigente),
    KEY ix_asignaciones_usuario (id_usuario, finaliza_en),
    CONSTRAINT fk_asignacion_unidad FOREIGN KEY (id_vehiculo) REFERENCES inventario_unidades (id_vehiculo),
    CONSTRAINT fk_asignacion_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario),
    CONSTRAINT ck_asignacion_fechas CHECK (finaliza_en IS NULL OR finaliza_en >= inicia_en)
) ENGINE=InnoDB;

CREATE TABLE autorizaciones_soporte (
    id_autorizacion BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_asignacion BIGINT UNSIGNED NOT NULL,
    id_administrador BIGINT UNSIGNED NOT NULL,
    concedida_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    vence_en DATETIME(6) NOT NULL,
    revocada_en DATETIME(6) NULL,
    KEY ix_soporte_asignacion_admin (id_asignacion, id_administrador, vence_en),
    CONSTRAINT fk_soporte_asignacion FOREIGN KEY (id_asignacion)
        REFERENCES asignaciones_vehiculo (id_asignacion),
    CONSTRAINT fk_soporte_admin FOREIGN KEY (id_administrador) REFERENCES usuarios (id_usuario),
    CONSTRAINT ck_soporte_fechas CHECK (
        vence_en > concedida_en AND (revocada_en IS NULL OR revocada_en >= concedida_en)
    )
) ENGINE=InnoDB;

-- Cada fila indica una demo privada. Las demos existentes siguen siendo de empresa.
CREATE TABLE propiedad_demo (
    id_demo INT NOT NULL PRIMARY KEY,
    id_usuario BIGINT UNSIGNED NOT NULL,
    CONSTRAINT fk_propiedad_demo FOREIGN KEY (id_demo) REFERENCES demos (id_demo),
    CONSTRAINT fk_propiedad_demo_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario)
) ENGINE=InnoDB;

-- Un vehículo admite una reserva pendiente de cierre, para cualquier tipo de operador.
-- La fila de un invitado representa además su sesión temporal.
CREATE TABLE reservas_control (
    id_reserva BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_vehiculo INT NOT NULL,
    id_sesion_usuario BIGINT UNSIGNED NULL,
    token_invitado_hash BINARY(32) NULL,
    inicia_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    vence_en DATETIME(6) NOT NULL,
    finaliza_en DATETIME(6) NULL,
    id_vehiculo_reservado INT GENERATED ALWAYS AS (
        CASE WHEN finaliza_en IS NULL THEN id_vehiculo END
    ) STORED,
    UNIQUE KEY uq_reserva_unidad_abierta (id_vehiculo_reservado),
    UNIQUE KEY uq_reserva_token_invitado (token_invitado_hash),
    KEY ix_reserva_cierre (finaliza_en, vence_en),
    CONSTRAINT fk_reserva_unidad FOREIGN KEY (id_vehiculo) REFERENCES inventario_unidades (id_vehiculo),
    CONSTRAINT fk_reserva_sesion FOREIGN KEY (id_sesion_usuario) REFERENCES sesiones_usuario (id_sesion),
    CONSTRAINT ck_reserva_operador CHECK (
        (id_sesion_usuario IS NOT NULL AND token_invitado_hash IS NULL)
        OR (id_sesion_usuario IS NULL AND token_invitado_hash IS NOT NULL)
    ),
    CONSTRAINT ck_reserva_fechas CHECK (
        vence_en > inicia_en AND (finaliza_en IS NULL OR finaliza_en >= inicia_en)
    )
) ENGINE=InnoDB;

CREATE TABLE credenciales_dispositivo (
    id_vehiculo INT NOT NULL PRIMARY KEY,
    token_hash BINARY(32) NOT NULL,
    emitida_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    revocada_en DATETIME(6) NULL,
    UNIQUE KEY uq_dispositivo_token (token_hash),
    CONSTRAINT fk_dispositivo_unidad FOREIGN KEY (id_vehiculo)
        REFERENCES inventario_unidades (id_vehiculo),
    CONSTRAINT ck_dispositivo_fechas CHECK (revocada_en IS NULL OR revocada_en >= emitida_en)
) ENGINE=InnoDB;

CREATE TABLE auditoria_administracion (
    id_evento BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    id_usuario BIGINT UNSIGNED NULL,
    id_reserva BIGINT UNSIGNED NULL,
    id_vehiculo INT NULL,
    accion VARCHAR(64) NOT NULL,
    detalle JSON NULL,
    ocurrio_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY ix_auditoria_unidad_fecha (id_vehiculo, ocurrio_en),
    KEY ix_auditoria_fecha (ocurrio_en, id_evento),
    CONSTRAINT fk_auditoria_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario),
    CONSTRAINT fk_auditoria_reserva FOREIGN KEY (id_reserva) REFERENCES reservas_control (id_reserva),
    CONSTRAINT fk_auditoria_unidad FOREIGN KEY (id_vehiculo) REFERENCES inventario_unidades (id_vehiculo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
