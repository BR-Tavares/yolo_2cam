import time
import threading
import sys
import os
import uvicorn

# Adiciona o diretório raiz ao sys.path para garantir imports consistentes
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from monitoramento_feira.config import config
from monitoramento_feira.banco import Database
from monitoramento_feira.captura import CameraManager
from monitoramento_feira.estado import TrajectoryState, EngagementState
from monitoramento_feira.modelo_trajetoria import ModeloTrajetoria
from monitoramento_feira.modelo_engajamento import ModeloEngajamento
import monitoramento_feira.radar_server as radar_server

class FeiraSystem:
    def __init__(self):
        self.config = config
        self.db = Database(self.config.db_path)
        self.camera_mgr = CameraManager(
            single_camera_mode=self.config.single_camera_mode,
            source_a=self.config.camera_a_source,
            source_b=self.config.camera_b_source
        )

        self.traj_state = TrajectoryState(self.db, timeout=self.config.session_timeout)
        self.eng_state = EngagementState(
            self.db,
            timeout=self.config.session_timeout,
            saturation_dwell=self.config.saturation_dwell_time,
            min_dwell=self.config.min_dwell_time
        )

        self.mod_traj = ModeloTrajetoria(
            src_pts=self.config.homografia_src_pts,
            dst_pts=self.config.homografia_dst_pts,
            zona_poligono=self.config.zona_poligono,
            inverter_eixo_x=self.config.inverter_eixo_x
        )


        self.mod_eng = ModeloEngajamento(
            yaw_limiar=self.config.yaw_limiar,
            pitch_limiar=self.config.pitch_limiar
        )

        # Injeta referências no servidor FastAPI
        radar_server.trajectory_state = self.traj_state
        radar_server.engagement_state = self.eng_state
        radar_server.camera_manager = self.camera_mgr
        radar_server.modelo_trajetoria = self.mod_traj
        radar_server.app_config = self.config

        self.running = False
        self.last_annotated_a = None
        self.last_annotated_b = None
        self.lock = threading.Lock()

    def start(self):
        self.running = True
        # Inicia loop de inferência em thread separada
        self.infer_thread = threading.Thread(target=self._inference_loop, name="Thread-Inference", daemon=True)
        self.infer_thread.start()

        # Inicia agregador periódico do SQLite
        self.agg_thread = threading.Thread(target=self._aggregator_loop, name="Thread-Aggregator", daemon=True)
        self.agg_thread.start()

        print("[FeiraSystem] Sistema de monitoramento inicializado.")
        print(f"[FeiraSystem] Modo de Câmera: {'Webcam Única (Multiplexada)' if self.config.single_camera_mode else '2 Câmeras Independentes'}")
        print(f"[FeiraSystem] Servidor Radar disponível em http://localhost:{self.config.api_port}/radar")
        print(f"[FeiraSystem] Tela de Engajamento em http://localhost:{self.config.api_port}/engajamento")

    def _inference_loop(self):
        last_traj_time = 0.0
        traj_interval = 1.0 / 12.0  # ~12 FPS para público (conforme especificação 10-15 FPS)

        last_eng_time = 0.0
        eng_interval = 1.0 / 10.0   # ~10 FPS para engajamento

        while self.running:
            now = time.time()

            # Pipeline A: Público / Trajetória
            if self.config.camera_a_enabled and (now - last_traj_time >= traj_interval):
                last_traj_time = now
                frame_a = self.camera_mgr.get_frame_a()
                if frame_a is not None:
                    dets_a, ann_a = self.mod_traj.processar(frame_a, draw_overlay=True)
                    with self.lock:
                        self.last_annotated_a = ann_a
                        radar_server.last_frame_a = ann_a

                    with self.eng_state.lock:
                        active_faces = list(self.eng_state.active.values())

                    alguem_olhando = any(f.get("facing", False) for f in active_faces)

                    for det in dets_a:
                        p_olhando = False
                        bx1, by1, bx2, by2 = det.get("bbox", [0, 0, 0, 0])
                        for f in active_faces:
                            if f.get("facing", False):
                                fb = f.get("bbox", [])
                                if len(fb) == 4:
                                    fcx = (fb[0] + fb[2]) / 2.0
                                    fcy = (fb[1] + fb[3]) / 2.0
                                    if (bx1 - 30 <= fcx <= bx2 + 30) and (by1 - 30 <= fcy <= by2 + 30):
                                        p_olhando = True
                                        break
                        if not p_olhando and (len(dets_a) == 1 or alguem_olhando):
                            p_olhando = alguem_olhando

                        self.traj_state.update_track(
                            track_id=det["track_id"],
                            pos_radar=det["pos_radar"],
                            na_zona=det["na_zona"],
                            olhando=p_olhando
                        )
                self.traj_state.cleanup_expired()


            # Pipeline B: Engajamento
            if self.config.camera_b_enabled and (now - last_eng_time >= eng_interval):
                last_eng_time = now
                frame_b = self.camera_mgr.get_frame_b()
                if frame_b is not None:
                    faces_b, ann_b = self.mod_eng.processar(frame_b, draw_overlay=True)
                    with self.lock:
                        self.last_annotated_b = ann_b
                        radar_server.last_frame_b = ann_b
                    for face in faces_b:
                        self.eng_state.update_face(
                            face_session_id=face["face_id"],
                            facing=face["facing"],
                            yaw=face["yaw"],
                            pitch=face["pitch"],
                            bbox=face["bbox"]
                        )
                self.eng_state.cleanup_expired()


            time.sleep(0.01)

    def _aggregator_loop(self):
        """Agrega janelas de 5 minutos periodicamente no SQLite."""
        while self.running:
            time.sleep(300) # 5 minutos
            try:
                self.db.agregar_janela(janela_segundos=300.0)
            except Exception as e:
                print(f"[Aggregator] Erro ao consolidar janela: {e}")

    def get_previews(self):
        with self.lock:
            return self.last_annotated_a, self.last_annotated_b

    def stop(self):
        self.running = False
        self.camera_mgr.stop()
        print("[FeiraSystem] Sistema finalizado.")

# Instância única para execução
system_instance = None

def get_system():
    global system_instance
    if system_instance is None:
        system_instance = FeiraSystem()
    return system_instance

if __name__ == "__main__":
    system = get_system()
    system.start()
    uvicorn.run(radar_server.app, host=config.api_host, port=config.api_port, log_level="warning")
