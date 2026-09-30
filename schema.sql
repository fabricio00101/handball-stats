DROP TABLE IF EXISTS Eventos_Juego;
DROP TABLE IF EXISTS Jugadores;
DROP TABLE IF EXISTS Partidos;
DROP TABLE IF EXISTS Plantel;
DROP TABLE IF EXISTS Equipos;

CREATE TABLE Equipos (
  id_equipo INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE,
  es_propio INTEGER NOT NULL DEFAULT 0 CHECK (es_propio IN (0,1)),
  activo INTEGER NOT NULL DEFAULT 1,
  creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE Plantel (
  id_plantel INTEGER PRIMARY KEY AUTOINCREMENT,
  id_equipo INTEGER NOT NULL REFERENCES Equipos(id_equipo),
  nombre TEXT NOT NULL,
  numero_habitual INTEGER,
  posicion_habitual TEXT NOT NULL DEFAULT 'CAMPO'
    CHECK (posicion_habitual IN ('PORTERO','CAMPO')),
  activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE Partidos (
    id_partido INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_equipo_a TEXT NOT NULL,
    nombre_equipo_b TEXT NOT NULL,
    id_equipo_a INTEGER REFERENCES Equipos(id_equipo),
    id_equipo_b INTEGER REFERENCES Equipos(id_equipo),
    competicion TEXT,
    estado TEXT DEFAULT 'PROGRAMADO',
    fecha_partido TEXT NOT NULL,
    marcador_final_a INTEGER DEFAULT 0,
    marcador_final_b INTEGER DEFAULT 0,
    segundos_jugados INTEGER NOT NULL DEFAULT 0,
    periodo_actual INTEGER NOT NULL DEFAULT 1,
    en_pausa INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE Jugadores (
    id_jugador INTEGER PRIMARY KEY AUTOINCREMENT,
    id_partido INTEGER REFERENCES Partidos(id_partido),
    id_plantel INTEGER REFERENCES Plantel(id_plantel),
    nombre TEXT NOT NULL,
    id_equipo TEXT NOT NULL,
    numero_camiseta INTEGER NOT NULL,
    posicion TEXT NOT NULL DEFAULT 'CAMPO',
    es_generico INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX ux_jug_partido_num ON Jugadores(id_partido, id_equipo, numero_camiseta);

CREATE TABLE Eventos_Juego (
    id_evento INTEGER PRIMARY KEY AUTOINCREMENT,
    id_partido INTEGER NOT NULL,
    id_jugador INTEGER NOT NULL,
    tipo_evento TEXT NOT NULL, 
    resultado TEXT, 
    tiempo_juego TEXT NOT NULL, 
    periodo INTEGER DEFAULT 1,
    coordenada_x REAL,
    coordenada_y REAL,
    zona_porteria TEXT,
    zona_origen TEXT,
    lado TEXT,
    client_event_id TEXT UNIQUE,
    creado_en TEXT NOT NULL DEFAULT (datetime('now')),
    anulado INTEGER NOT NULL DEFAULT 0,
    anulado_en TEXT,
    generado_por TEXT,
    segundo_absoluto INTEGER,
    id_portero INTEGER REFERENCES Jugadores(id_jugador),
    distancia TEXT,
    es_7m INTEGER NOT NULL DEFAULT 0,
    es_contraataque INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (id_partido) REFERENCES Partidos (id_partido),
    FOREIGN KEY (id_jugador) REFERENCES Jugadores (id_jugador)
);

CREATE INDEX idx_eventos_partido ON Eventos_Juego(id_partido, id_evento);
CREATE INDEX idx_eventos_jugador ON Eventos_Juego(id_jugador);
