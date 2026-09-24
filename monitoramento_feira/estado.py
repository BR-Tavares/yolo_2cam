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
        with self.lock:
            if track_id not in self.active:
                self.active[track_id] = {
                    "start_ts": now,
                    "last_seen": now,
                    "trail": [pos_radar],
                    "zone_enter_ts": now if na_zona else None,
                    "zone_time_total": 0.0,
                    "na_zona": na_zona,
                    "olhando": olhando,
                    "current_pos": pos_radar
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


    def cleanup_expired(self):
        now = time.time()
        expired_sessions = []
        with self.lock:
            for track_id, data in list(self.active.items()):
                if now - data["last_seen"] > self.timeout:
                    expired_sessions.append((
                        track_id,
                        data["start_ts"],
                        data["last_seen"],
                        data["zone_time_total"]
                    ))
                    del self.active[track_id]

        for s in expired_sessions:
            try:
                self.db.salvar_sessao_trajetoria(
                    track_id=s[0],
                    inicio_ts=s[1],
                    fim_ts=s[2],
                    tempo_na_zona=s[3]
                )
            except Exception as e:
                print(f"[TrajectoryState] Erro ao persistir sessão {s[0]}: {e}")

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
        with self.lock:
            if face_session_id not in self.active:
                self.active[face_session_id] = {
                    "start_ts": now,
                    "last_seen": now,
                    "facing_time": 0.0,
                    "dwell_time": 0.0,
                    "facing": facing,
                    "yaw": yaw,
                    "pitch": pitch,
                    "bbox": bbox,
                    "engagement_score": 0.0
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

    def cleanup_expired(self):
        now = time.time()
        expired_sessions = []
        with self.lock:
            for fid, data in list(self.active.items()):
                if now - data["last_seen"] > self.timeout:
                    # Só persiste se dwell_time >= min_dwell (conforme Seção 5 e 11)
                    if data["dwell_time"] >= self.min_dwell:
                        expired_sessions.append((
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
                    sessao_id=s[0],
                    inicio_ts=s[1],
                    fim_ts=s[2],
                    dwell_time=s[3],
                    facing_time=s[4],
                    engagement_score=s[5]
                )
            except Exception as e:
                print(f"[EngagementState] Erro ao persistir engajamento {s[0]}: {e}")

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

