import sqlite3
import time
from typing import Optional, List, Dict, Any

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessoes_trajetoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    inicio_ts REAL,
    fim_ts REAL,
    tempo_na_zona REAL
);

CREATE TABLE IF NOT EXISTS sessoes_engajamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id TEXT,
    inicio_ts REAL,
    fim_ts REAL,
    dwell_time REAL,
    facing_time REAL,
    engagement_score REAL
);

CREATE TABLE IF NOT EXISTS agregados_janela (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    janela_inicio REAL,
    janela_fim REAL,
    visitantes_unicos INTEGER,
    tempo_medio_zona REAL,
    engajamentos_validos INTEGER,
    score_medio REAL
);
"""

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    def salvar_sessao_trajetoria(self, track_id: int, inicio_ts: float, fim_ts: float, tempo_na_zona: float):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessoes_trajetoria (track_id, inicio_ts, fim_ts, tempo_na_zona)
                VALUES (?, ?, ?, ?)
                """,
                (int(track_id), float(inicio_ts), float(fim_ts), float(tempo_na_zona))
            )
            conn.commit()

    def salvar_sessao_engajamento(self, sessao_id: str, inicio_ts: float, fim_ts: float,
                                  dwell_time: float, facing_time: float, engagement_score: float):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessoes_engajamento (sessao_id, inicio_ts, fim_ts, dwell_time, facing_time, engagement_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(sessao_id), float(inicio_ts), float(fim_ts), float(dwell_time), float(facing_time), float(engagement_score))
            )
            conn.commit()

    def agregar_janela(self, janela_segundos: float = 300.0) -> Optional[int]:
        """Consolida os dados dos últimos N minutos na tabela agregados_janela."""
        agora = time.time()
        inicio_janela = agora - janela_segundos

        with self._get_connection() as conn:
            cur = conn.cursor()
            # Visitantes únicos e tempo médio na zona
            cur.execute(
                """
                SELECT COUNT(DISTINCT track_id) as unicos, AVG(tempo_na_zona) as media_zona
                FROM sessoes_trajetoria
                WHERE fim_ts >= ? AND fim_ts <= ?
                """,
                (inicio_janela, agora)
            )
            row_traj = cur.fetchone()
            visitantes_unicos = row_traj["unicos"] if row_traj and row_traj["unicos"] else 0
            tempo_medio_zona = float(row_traj["media_zona"]) if row_traj and row_traj["media_zona"] else 0.0

            # Engajamentos válidos (dwell_time >= 3s conforme Seção 5 e 11) e score médio
            cur.execute(
                """
                SELECT COUNT(*) as validos, AVG(engagement_score) as media_score
                FROM sessoes_engajamento
                WHERE fim_ts >= ? AND fim_ts <= ? AND dwell_time >= 3.0
                """,
                (inicio_janela, agora)
            )
            row_eng = cur.fetchone()
            engajamentos_validos = row_eng["validos"] if row_eng and row_eng["validos"] else 0
            score_medio = float(row_eng["media_score"]) if row_eng and row_eng["media_score"] else 0.0

            cur.execute(
                """
                INSERT INTO agregados_janela (janela_inicio, janela_fim, visitantes_unicos, tempo_medio_zona, engajamentos_validos, score_medio)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (inicio_janela, agora, visitantes_unicos, tempo_medio_zona, engajamentos_validos, score_medio)
            )
            conn.commit()
            return cur.lastrowid

    def obter_resumo_geral(self) -> Dict[str, Any]:
        """Obtém totais gerais acumulados para o painel analítico."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(DISTINCT track_id) as total_visitantes, AVG(tempo_na_zona) as media_tempo_zona FROM sessoes_trajetoria")
            r1 = cur.fetchone()

            cur.execute("SELECT COUNT(*) as total_engajados, AVG(dwell_time) as media_dwell, AVG(engagement_score) as media_score FROM sessoes_engajamento WHERE dwell_time >= 3.0")
            r2 = cur.fetchone()

            return {
                "total_visitantes": r1["total_visitantes"] or 0,
                "tempo_medio_zona": round(r1["media_tempo_zona"] or 0.0, 1),
                "total_engajamentos_validos": r2["total_engajados"] or 0,
                "dwell_medio": round(r2["media_dwell"] or 0.0, 1),
                "score_medio": round(r2["media_score"] or 0.0, 2)
            }
