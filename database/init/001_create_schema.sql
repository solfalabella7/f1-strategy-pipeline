-- =============================================================================
-- F1 Strategy Pipeline - OpenF1 RAW Data Layer
-- Target Database: PostgreSQL 16
-- Description: Creación del esquema RAW correspondiente a los datos
--              obtenidos directamente de los endpoints de la API OpenF1.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. TABLA: circuits
-- Entidad de catálogo para los circuitos de Fórmula 1.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS circuits (
    circuit_key INTEGER PRIMARY KEY,
    circuit_short_name VARCHAR(100) NOT NULL,
    circuit_type VARCHAR(100),
    circuit_info_url TEXT,
    circuit_image TEXT,
    location VARCHAR(100),
    country_key INTEGER,
    country_code VARCHAR(10),
    country_name VARCHAR(100)
);

COMMENT ON TABLE circuits IS 'Catálogo de circuitos de F1 obtenidos de la metadata de OpenF1.';

-- -----------------------------------------------------------------------------
-- 2. TABLA: meetings
-- Representa un fin de semana de Gran Premio o jornada de test.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meetings (
    meeting_key INTEGER PRIMARY KEY,
    circuit_key INTEGER REFERENCES circuits(circuit_key) ON DELETE SET NULL,
    circuit_short_name VARCHAR(100),
    circuit_type VARCHAR(100),
    circuit_info_url TEXT,
    circuit_image TEXT,
    country_code VARCHAR(10),
    country_flag TEXT,
    country_key INTEGER,
    country_name VARCHAR(100),
    date_start TIMESTAMPTZ NOT NULL,
    date_end TIMESTAMPTZ NOT NULL,
    gmt_offset VARCHAR(20),
    location VARCHAR(100),
    meeting_name VARCHAR(255) NOT NULL,
    meeting_official_name VARCHAR(255),
    year INTEGER NOT NULL,
    is_cancelled BOOLEAN DEFAULT FALSE
);

COMMENT ON TABLE meetings IS 'Información de eventos y fines de semana de carrera (Grands Prix / Tests).';

-- -----------------------------------------------------------------------------
-- 3. TABLA: sessions
-- Sesiones oficiales de pista (Prácticas libres, Clasificación, Sprint, Carrera).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_key INTEGER PRIMARY KEY,
    meeting_key INTEGER NOT NULL REFERENCES meetings(meeting_key) ON DELETE CASCADE,
    circuit_key INTEGER REFERENCES circuits(circuit_key) ON DELETE SET NULL,
    circuit_short_name VARCHAR(100),
    country_code VARCHAR(10),
    country_key INTEGER,
    country_name VARCHAR(100),
    date_start TIMESTAMPTZ NOT NULL,
    date_end TIMESTAMPTZ NOT NULL,
    gmt_offset VARCHAR(20),
    location VARCHAR(100),
    session_name VARCHAR(100) NOT NULL,
    session_type VARCHAR(50) NOT NULL,
    year INTEGER NOT NULL,
    is_cancelled BOOLEAN DEFAULT FALSE
);

COMMENT ON TABLE sessions IS 'Sesiones específicas de cada fin de semana (FP1, FP2, FP3, Qualy, Sprint, Race).';

-- -----------------------------------------------------------------------------
-- 4. TABLA: drivers
-- Información de pilotos participantes por sesión (número, equipo, siglas).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS drivers (
    session_key INTEGER NOT NULL REFERENCES sessions(session_key) ON DELETE CASCADE,
    meeting_key INTEGER NOT NULL REFERENCES meetings(meeting_key) ON DELETE CASCADE,
    driver_number INTEGER NOT NULL,
    broadcast_name VARCHAR(100),
    full_name VARCHAR(150) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    name_acronym VARCHAR(10),
    team_name VARCHAR(100),
    team_colour VARCHAR(20),
    headshot_url TEXT,
    country_code VARCHAR(10),
    PRIMARY KEY (session_key, driver_number)
);

COMMENT ON TABLE drivers IS 'Detalle de pilotos y escuderías por sesión de F1 según OpenF1.';

-- -----------------------------------------------------------------------------
-- 5. TABLA: laps
-- Registro detallado vuelta por vuelta para cada piloto.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS laps (
    session_key INTEGER NOT NULL,
    meeting_key INTEGER NOT NULL REFERENCES meetings(meeting_key) ON DELETE CASCADE,
    driver_number INTEGER NOT NULL,
    lap_number INTEGER NOT NULL,
    date_start TIMESTAMPTZ,
    duration_sector_1 DOUBLE PRECISION,
    duration_sector_2 DOUBLE PRECISION,
    duration_sector_3 DOUBLE PRECISION,
    i1_speed INTEGER,
    i2_speed INTEGER,
    st_speed INTEGER,
    is_pit_out_lap BOOLEAN DEFAULT FALSE,
    lap_duration DOUBLE PRECISION,
    segments_sector_1 INTEGER[],
    segments_sector_2 INTEGER[],
    segments_sector_3 INTEGER[],
    PRIMARY KEY (session_key, driver_number, lap_number),
    FOREIGN KEY (session_key, driver_number) REFERENCES drivers(session_key, driver_number) ON DELETE CASCADE,
    FOREIGN KEY (session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
);

COMMENT ON TABLE laps IS 'Tiempos de vuelta, sectores, velocidades intermedias y mini-sectores por piloto.';

-- -----------------------------------------------------------------------------
-- 6. TABLA: stints
-- Información de stints de neumáticos utilizados (compuesto, vueltas, edad inicial).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stints (
    session_key INTEGER NOT NULL,
    meeting_key INTEGER NOT NULL REFERENCES meetings(meeting_key) ON DELETE CASCADE,
    driver_number INTEGER NOT NULL,
    stint_number INTEGER NOT NULL,
    lap_start INTEGER,
    lap_end INTEGER,
    compound VARCHAR(20),
    tyre_age_at_start INTEGER,
    PRIMARY KEY (session_key, driver_number, stint_number),
    FOREIGN KEY (session_key, driver_number) REFERENCES drivers(session_key, driver_number) ON DELETE CASCADE,
    FOREIGN KEY (session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
);

COMMENT ON TABLE stints IS 'Uso de neumáticos por piloto: compuesto (SOFT, MEDIUM, HARD, etc.), inicio, fin y edad del neumático.';

-- -----------------------------------------------------------------------------
-- 7. TABLA: pit_stops
-- Eventos y duraciones de paradas en boxes (pit lane, tiempo detenido).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pit_stops (
    session_key INTEGER NOT NULL,
    meeting_key INTEGER NOT NULL REFERENCES meetings(meeting_key) ON DELETE CASCADE,
    driver_number INTEGER NOT NULL,
    lap_number INTEGER NOT NULL,
    date TIMESTAMPTZ NOT NULL,
    pit_duration DOUBLE PRECISION,
    lane_duration DOUBLE PRECISION,
    stop_duration DOUBLE PRECISION,
    PRIMARY KEY (session_key, driver_number, lap_number),
    FOREIGN KEY (session_key, driver_number) REFERENCES drivers(session_key, driver_number) ON DELETE CASCADE,
    FOREIGN KEY (session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
);

COMMENT ON TABLE pit_stops IS 'Tiempos de pit lane y parada en boxes por vuelta de cada piloto.';

-- -----------------------------------------------------------------------------
-- 8. TABLA: weather
-- Condiciones meteorológicas y de pista muestreadas a lo largo de la sesión.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weather (
    session_key INTEGER NOT NULL REFERENCES sessions(session_key) ON DELETE CASCADE,
    meeting_key INTEGER NOT NULL REFERENCES meetings(meeting_key) ON DELETE CASCADE,
    date TIMESTAMPTZ NOT NULL,
    air_temperature DOUBLE PRECISION,
    track_temperature DOUBLE PRECISION,
    humidity DOUBLE PRECISION,
    pressure DOUBLE PRECISION,
    rainfall SMALLINT,
    wind_direction INTEGER,
    wind_speed DOUBLE PRECISION,
    PRIMARY KEY (session_key, date)
);

COMMENT ON TABLE weather IS 'Datos climáticos en pista: temperatura ambiente/pista, humedad, lluvia y viento.';

-- -----------------------------------------------------------------------------
-- 9. TABLA: positions
-- Evolución temporal de las posiciones en pista por piloto.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS positions (
    session_key INTEGER NOT NULL,
    meeting_key INTEGER NOT NULL REFERENCES meetings(meeting_key) ON DELETE CASCADE,
    driver_number INTEGER NOT NULL,
    date TIMESTAMPTZ NOT NULL,
    position INTEGER NOT NULL,
    PRIMARY KEY (session_key, driver_number, date),
    FOREIGN KEY (session_key, driver_number) REFERENCES drivers(session_key, driver_number) ON DELETE CASCADE,
    FOREIGN KEY (session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
);

COMMENT ON TABLE positions IS 'Historial de cambios de posición en pista para cada piloto durante la sesión.';

-- -----------------------------------------------------------------------------
-- 10. TABLA: race_control
-- Mensajes, banderas, estados de safety car e incidentes reportados por dirección de carrera.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS race_control (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    meeting_key INTEGER NOT NULL REFERENCES meetings(meeting_key) ON DELETE CASCADE,
    session_key INTEGER NOT NULL REFERENCES sessions(session_key) ON DELETE CASCADE,
    date TIMESTAMPTZ NOT NULL,
    driver_number INTEGER,
    lap_number INTEGER,
    category VARCHAR(50),
    flag VARCHAR(50),
    scope VARCHAR(50),
    sector INTEGER,
    qualifying_phase VARCHAR(20),
    message TEXT
);

COMMENT ON TABLE race_control IS 'Eventos de dirección de carrera (banderas amarillas/rojas, SC, VSC, sanciones e investigaciones).';

-- -----------------------------------------------------------------------------
-- 11. TABLA: intervals
-- Brechas temporales (gap al líder e intervalo respecto al auto de adelante).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intervals (
    session_key INTEGER NOT NULL,
    meeting_key INTEGER NOT NULL REFERENCES meetings(meeting_key) ON DELETE CASCADE,
    driver_number INTEGER NOT NULL,
    date TIMESTAMPTZ NOT NULL,
    gap_to_leader DOUBLE PRECISION,
    "interval" DOUBLE PRECISION,
    PRIMARY KEY (session_key, driver_number, date),
    FOREIGN KEY (session_key, driver_number) REFERENCES drivers(session_key, driver_number) ON DELETE CASCADE,
    FOREIGN KEY (session_key) REFERENCES sessions(session_key) ON DELETE CASCADE
);

COMMENT ON TABLE intervals IS 'Gaps de tiempo en vivo hacia el líder y respecto al piloto precedente.';

-- =============================================================================
-- ÍNDICES PARA CONSULTAS Y RELACIONES FRECUENTES
-- =============================================================================

-- meetings & sessions
CREATE INDEX IF NOT EXISTS idx_meetings_year ON meetings(year);
CREATE INDEX IF NOT EXISTS idx_meetings_circuit_key ON meetings(circuit_key);

CREATE INDEX IF NOT EXISTS idx_sessions_meeting_key ON sessions(meeting_key);
CREATE INDEX IF NOT EXISTS idx_sessions_circuit_key ON sessions(circuit_key);
CREATE INDEX IF NOT EXISTS idx_sessions_date_start ON sessions(date_start);
CREATE INDEX IF NOT EXISTS idx_sessions_type ON sessions(session_type);

-- drivers
CREATE INDEX IF NOT EXISTS idx_drivers_session_key ON drivers(session_key);
CREATE INDEX IF NOT EXISTS idx_drivers_meeting_key ON drivers(meeting_key);
CREATE INDEX IF NOT EXISTS idx_drivers_driver_number ON drivers(driver_number);
CREATE INDEX IF NOT EXISTS idx_drivers_team_name ON drivers(team_name);

-- laps
CREATE INDEX IF NOT EXISTS idx_laps_session_driver ON laps(session_key, driver_number);
CREATE INDEX IF NOT EXISTS idx_laps_meeting_key ON laps(meeting_key);
CREATE INDEX IF NOT EXISTS idx_laps_driver_number ON laps(driver_number);
CREATE INDEX IF NOT EXISTS idx_laps_lap_number ON laps(lap_number);
CREATE INDEX IF NOT EXISTS idx_laps_date_start ON laps(date_start);

-- stints
CREATE INDEX IF NOT EXISTS idx_stints_session_driver ON stints(session_key, driver_number);
CREATE INDEX IF NOT EXISTS idx_stints_meeting_key ON stints(meeting_key);
CREATE INDEX IF NOT EXISTS idx_stints_driver_number ON stints(driver_number);
CREATE INDEX IF NOT EXISTS idx_stints_compound ON stints(compound);

-- pit_stops
CREATE INDEX IF NOT EXISTS idx_pit_stops_session_driver ON pit_stops(session_key, driver_number);
CREATE INDEX IF NOT EXISTS idx_pit_stops_meeting_key ON pit_stops(meeting_key);
CREATE INDEX IF NOT EXISTS idx_pit_stops_driver_number ON pit_stops(driver_number);
CREATE INDEX IF NOT EXISTS idx_pit_stops_lap_number ON pit_stops(lap_number);
CREATE INDEX IF NOT EXISTS idx_pit_stops_date ON pit_stops(date);

-- weather
CREATE INDEX IF NOT EXISTS idx_weather_session_key ON weather(session_key);
CREATE INDEX IF NOT EXISTS idx_weather_meeting_key ON weather(meeting_key);
CREATE INDEX IF NOT EXISTS idx_weather_date ON weather(date);

-- positions
CREATE INDEX IF NOT EXISTS idx_positions_session_driver ON positions(session_key, driver_number);
CREATE INDEX IF NOT EXISTS idx_positions_meeting_key ON positions(meeting_key);
CREATE INDEX IF NOT EXISTS idx_positions_driver_number ON positions(driver_number);
CREATE INDEX IF NOT EXISTS idx_positions_date ON positions(date);
CREATE INDEX IF NOT EXISTS idx_positions_position ON positions(position);

-- race_control
CREATE INDEX IF NOT EXISTS idx_race_control_session_key ON race_control(session_key);
CREATE INDEX IF NOT EXISTS idx_race_control_meeting_key ON race_control(meeting_key);
CREATE INDEX IF NOT EXISTS idx_race_control_driver_number ON race_control(driver_number);
CREATE INDEX IF NOT EXISTS idx_race_control_date ON race_control(date);
CREATE INDEX IF NOT EXISTS idx_race_control_category ON race_control(category);
CREATE INDEX IF NOT EXISTS idx_race_control_flag ON race_control(flag);

-- intervals
CREATE INDEX IF NOT EXISTS idx_intervals_session_driver ON intervals(session_key, driver_number);
CREATE INDEX IF NOT EXISTS idx_intervals_meeting_key ON intervals(meeting_key);
CREATE INDEX IF NOT EXISTS idx_intervals_driver_number ON intervals(driver_number);
CREATE INDEX IF NOT EXISTS idx_intervals_date ON intervals(date);
