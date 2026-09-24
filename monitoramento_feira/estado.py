import time
import threading
from typing import Dict, Any, List, Optional
from monitoramento_feira.banco import Database

class TrajectoryState:
    """Gerencia o estado em memória dos rastros de pessoas na área da webcam elevada."""
    def __init__(self, db: Database, timeout: float = 2.0):
        self.db = db
        self.timeout = timeout
        self.active: Dict[int, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def update_track(self, track_id: int, pos_radar: List[float], na_zona: bool, olhando: bool = False):
        now = time.time()
        to_sync = None
        with self.lock:
            if track_id not in self.active:
                sessao_uid = f"traj_{track_id}_{int(now)}"
                self.active[track_id] = {
                    "sessao_uid": sessao_uid,
                    "start_ts": now,
                    "last_seen": now,
                    "trail": [pos_radar],
                    "zone_enter_ts": now if na_zona else None,
                    "zone_time_total": 0.0,
                    "na_zona": na_zona,
                    "olhando": olhando,
                    "current_pos": pos_radar,
                    "last_db_sync": now
                }
            else:
                data = self.active[track_id]
                delta = now - data["last_seen"]
                data["last_seen"] = now
                data["current_pos"] = pos_radar
                data["olhando"] = olhando
                # Mantém os últimos 25 pontos para efeito cauda de cometa
                data["trail"].append(pos_radar)
                if len(data["trail"]) > 25:
                    data["trail"].pop(0)

                # Controle de permanência na zona
                if na_zona:
                    if data["zone_enter_ts"] is None:
                        data["zone_enter_ts"] = now
                    else:
                        data["zone_time_total"] += delta
                else:
                    data["zone_enter_ts"] = None
                data["na_zona"] = na_zona

                # Sincronização contínua com SQLite (a cada 2.5s se já tiver pelo menos 1.0s de passagem)
                if (now - data["start_ts"] >= 1.0) and (now - data.get("last_db_sync", 0.0) >= 2.5):
                    data["last_db_sync"] = now
                    to_sync = (data["sessao_uid"], track_id, data["start_ts"], now, data["zone_time_total"])

        if to_sync:
            try:
                self.db.salvar_sessao_trajetoria(
                    track_id=to_sync[1],
                    inicio_ts=to_sync[2],
                    fim_ts=to_sync[3],
                    tempo_na_zona=to_sync[4],
                    sessao_uid=to_sync[0]
                )
            except Exception:
                pass

    def sincronizar_ativos_agora(self):
        """Persiste imediatamente todas as trajetórias ativas relevantes no SQLite."""
        now = time.time()
        to_save = []
        with self.lock:
            for track_id, data in self.active.items():
                if now - data["start_ts"] >= 1.0:
                    to_save.append((
                        data.get("sessao_uid", f"traj_{track_id}_{int(data['start_ts'])}"),
                        track_id,
                        data["start_ts"],
                        now,
                        data["zone_time_total"]
                    ))
        for s in to_save:
            try:
                self.db.salvar_sessao_trajetoria(
                    track_id=s[1],
                    inicio_ts=s[2],
                    fim_ts=s[3],
                    tempo_na_zona=s[4],
                    sessao_uid=s[0]
                )
            except Exception:
                pass

    def cleanup_expired(self):
        now = time.time()
        expired_sessions = []
        with self.lock:
            for track_id, data in list(self.active.items()):
                if now - data["last_seen"] > self.timeout:
                    if now - data["start_ts"] >= 1.0:
                        expired_sessions.append((
                            data.get("sessao_uid", f"traj_{track_id}_{int(data['start_ts'])}"),
                            track_id,
                            data["start_ts"],
                            data["last_seen"],
                            data["zone_time_total"]
                        ))
                    del self.active[track_id]

        for s in expired_sessions:
            try:
                self.db.salvar_sessao_trajetoria(
                    track_id=s[1],
                    inicio_ts=s[2],
                    fim_ts=s[3],
                    tempo_na_zona=s[4],
                    sessao_uid=s[0]
                )
            except Exception as e:
                print(f"[TrajectoryState] Erro ao persistir sessão {s[1]}: {e}")

    def get_snapshot(self) -> List[Dict[str, Any]]:
        with self.lock:
            snapshot = []
            for track_id, data in self.active.items():
                snapshot.append({
                    "track_id": track_id,
                    "pos": data["current_pos"],
                    "trail": list(data["trail"]),
                    "na_zona": data["na_zona"],
                    "olhando": data.get("olhando", False),
                    "tempo_zona": round(data["zone_time_total"], 1)
                })

            return snapshot


class EngagementState:
    """Gerencia o estado em memória das sessões de engajamento na câmera frontal."""
    def __init__(self, db: Database, timeout: float = 2.0, saturation_dwell: float = 30.0, min_dwell: float = 3.0):
        self.db = db
        self.timeout = timeout
        self.saturation_dwell = saturation_dwell
        self.min_dwell = min_dwell
        self.active: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def update_face(self, face_session_id: str, facing: bool, yaw: float, pitch: float, bbox: List[float]):
        now = time.time()
        to_sync = None
        with self.lock:
            if face_session_id not in self.active:
                sessao_uid = f"eng_{face_session_id}_{int(now)}"
                self.active[face_session_id] = {
                    "sessao_uid": sessao_uid,
                    "start_ts": now,
                    "last_seen": now,
                    "facing_time": 0.0,
                    "dwell_time": 0.0,
                    "facing": facing,
                    "yaw": yaw,
                    "pitch": pitch,
                    "bbox": bbox,
                    "engagement_score": 0.0,
                    "last_db_sync": 0.0
                }
            else:
                data = self.active[face_session_id]
                delta = now - data["last_seen"]
                data["last_seen"] = now
                data["dwell_time"] = now - data["start_ts"]
                data["facing"] = facing
                data["yaw"] = yaw
                data["pitch"] = pitch
                data["bbox"] = bbox

                if facing:
                    data["facing_time"] += delta

                # engagement_score = (facing_time / dwell_time) * min(1.0, dwell_time / saturation_dwell)
                if data["dwell_time"] > 0:
                    proporcao = min(1.0, data["facing_time"] / data["dwell_time"])
                    saturacao = min(1.0, data["dwell_time"] / self.saturation_dwell)
                    data["engagement_score"] = round(proporcao * saturacao, 3)

                # Se a pessoa já atingiu min_dwell (>= 3s), sincroniza periodicamente no SQLite (a cada 2.0s)
                if (data["dwell_time"] >= self.min_dwell) and (now - data.get("last_db_sync", 0.0) >= 2.0):
                    data["last_db_sync"] = now
                    to_sync = (
                        data["sessao_uid"],
                        face_session_id,
                        data["start_ts"],
                        now,
                        data["dwell_time"],
                        data["facing_time"],
                        data["engagement_score"]
                    )

        if to_sync:
            try:
                self.db.salvar_sessao_engajamento(
                    sessao_id=to_sync[1],
                    inicio_ts=to_sync[2],
                    fim_ts=to_sync[3],
                    dwell_time=to_sync[4],
                    facing_time=to_sync[5],
                    engagement_score=to_sync[6],
                    sessao_uid=to_sync[0]
                )
            except Exception:
                pass

    def sincronizar_ativos_agora(self):
        """Persiste imediatamente todos os engajamentos válidos ativos no SQLite."""
        now = time.time()
        to_save = []
        with self.lock:
            for fid, data in self.active.items():
                if data["dwell_time"] >= self.min_dwell:
                    to_save.append((
                        data.get("sessao_uid", f"eng_{fid}_{int(data['start_ts'])}"),
                        fid,
                        data["start_ts"],
                        now,
                        data["dwell_time"],
                        data["facing_time"],
                        data["engagement_score"]
                    ))
        for s in to_save:
            try:
                self.db.salvar_sessao_engajamento(
                    sessao_id=s[1],
                    inicio_ts=s[2],
                    fim_ts=s[3],
                    dwell_time=s[4],
                    facing_time=s[5],
                    engagement_score=s[6],
                    sessao_uid=s[0]
                )
            except Exception:
                pass

    def cleanup_expired(self):
        now = time.time()
        expired_sessions = []
        with self.lock:
            for fid, data in list(self.active.items()):
                if now - data["last_seen"] > self.timeout:
                    # Só persiste se dwell_time >= min_dwell (conforme Seção 5 e 11)
                    if data["dwell_time"] >= self.min_dwell:
                        expired_sessions.append((
                            data.get("sessao_uid", f"eng_{fid}_{int(data['start_ts'])}"),
                            fid,
                            data["start_ts"],
                            data["last_seen"],
                            data["dwell_time"],
                            data["facing_time"],
                            data["engagement_score"]
                        ))
                    del self.active[fid]

        for s in expired_sessions:
            try:
                self.db.salvar_sessao_engajamento(
                    sessao_id=s[1],
                    inicio_ts=s[2],
                    fim_ts=s[3],
                    dwell_time=s[4],
                    facing_time=s[5],
                    engagement_score=s[6],
                    sessao_uid=s[0]
                )
            except Exception as e:
                print(f"[EngagementState] Erro ao persistir engajamento {s[1]}: {e}")

    def get_snapshot(self) -> Dict[str, Any]:
        with self.lock:
            if not self.active:
                return {
                    "active": False,
                    "count": 0,
                    "total_olhando": 0,
                    "energia_coletiva": 0.0,
                    "principal": None,
                    "pessoas": []
                }

            sessions = list(self.active.values())
            total_olhando = sum(1 for s in sessions if s.get("facing", False))
            principal = max(sessions, key=lambda x: x["dwell_time"])
            
            # Energia coletiva: soma ponderada das pessoas engajadas (atinge 100% com 2+ olhares conectados)
            energia_coletiva = min(1.0, round(total_olhando * 0.5 + principal.get("engagement_score", 0.0) * 0.5, 2))

            pessoas_list = []
            for fid, s in self.active.items():
                pessoas_list.append({
                    "id": fid,
                    "facing": s.get("facing", False),
                    "dwell_time": round(s.get("dwell_time", 0.0), 1),
                    "facing_time": round(s.get("facing_time", 0.0), 1),
                    "score": s.get("engagement_score", 0.0)
                })

            return {
                "active": True,
                "count": len(self.active),
                "total_olhando": total_olhando,
                "energia_coletiva": energia_coletiva,
                "principal": {
                    "dwell_time": round(principal["dwell_time"], 1),
                    "facing": principal["facing"],
                    "facing_time": round(principal["facing_time"], 1),
                    "score": principal["engagement_score"],
                    "yaw": round(principal["yaw"], 1),
                    "pitch": round(principal["pitch"], 1)
                },
                "pessoas": pessoas_list
            }

