DROP TABLE IF EXISTS Eventos_Juego;
DROP TABLE IF EXISTS Jugadores;
DROP TABLE IF EXISTS Partidos;

CREATE TABLE Partidos (
    id_partido INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_equipo_a TEXT NOT NULL,
    nombre_equipo_b TEXT NOT NULL,
    fecha_partido TEXT NOT NULL,
    marcador_final_a INTEGER DEFAULT 0,
    marcador_final_b INTEGER DEFAULT 0
);

CREATE TABLE Jugadores (
    id_jugador INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    id_equipo TEXT NOT NULL,
    numero_camiseta INTEGER NOT NULL
);

CREATE TABLE Eventos_Juego (
    id_evento INTEGER PRIMARY KEY AUTOINCREMENT,
    id_partido INTEGER,
    id_jugador INTEGER,
    tipo_evento TEXT NOT NULL, 
    resultado TEXT, 
    tiempo_juego TEXT NOT NULL, 
    periodo INTEGER DEFAULT 1,
    coordenada_x REAL,
    coordenada_y REAL,
    zona_porteria TEXT,
    FOREIGN KEY (id_partido) REFERENCES Partidos (id_partido),
    FOREIGN KEY (id_jugador) REFERENCES Jugadores (id_jugador)
);
