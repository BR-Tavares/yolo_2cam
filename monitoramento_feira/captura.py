import cv2
import threading
import time
from typing import Optional, Union, Tuple
import numpy as np

class VideoSource:
    """Captura de vídeo em thread dedicada para evitar bloqueio e latência de buffer."""
    def __init__(self, source_id: Union[int, str], name: str = "Camera"):
        self.source_id = source_id
        self.name = name
        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.lock = threading.Lock()
        self.running = False
        self.connected = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, name=f"Thread-{self.name}", daemon=True)
        self.thread.start()

    def _open_capture(self) -> bool:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        
        # Se for índice numérico no Windows, usar CAP_DSHOW para inicialização mais estável
        if isinstance(self.source_id, int) or (isinstance(self.source_id, str) and self.source_id.isdigit()):
            idx = int(self.source_id)
            self.cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(self.source_id)

        if self.cap and self.cap.isOpened():
            # Configurações de buffer mínimo para baixa latência
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.connected = True
            print(f"[{self.name}] Câmera conectada com sucesso (origem: {self.source_id})")
            return True
        else:
            self.connected = False
            print(f"[{self.name}] Falha ao abrir câmera (origem: {self.source_id})")
            return False

    def _loop(self):
        retry_delay = 2.0
        last_retry = 0.0

        while self.running:
            if not self.connected or self.cap is None or not self.cap.isOpened():
                now = time.time()
                if now - last_retry >= retry_delay:
                    last_retry = now
                    self._open_capture()
                time.sleep(0.1)
                continue

            ok, frame = self.cap.read()
            if ok and frame is not None:
                with self.lock:
                    self.latest_frame = frame
                # Pequena pausa para ceder CPU e sincronizar com FPS nativo
                time.sleep(0.01)
            else:
                self.connected = False
                time.sleep(0.05)

    def get_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

    def is_alive(self) -> bool:
        return self.connected and (self.latest_frame is not None)

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
        self.connected = False
        print(f"[{self.name}] Câmera finalizada.")


class CameraManager:
    """Gerenciador unificado para Fonte A (Público) e Fonte B (Engajamento)."""
    def __init__(self, single_camera_mode: bool = True, source_a: Union[int, str] = 0, source_b: Union[int, str] = 1):
        self.single_camera_mode = single_camera_mode
        self.source_a_id = source_a
        self.source_b_id = source_b

        self.cam_a: Optional[VideoSource] = None
        self.cam_b: Optional[VideoSource] = None
        self._init_sources()

    def _init_sources(self):
        # Para modo de 1 webcam: abre apenas cam_a e reutiliza seu feed para cam_b
        self.cam_a = VideoSource(self.source_a_id, name="FonteA-Publico")
        self.cam_a.start()

        if not self.single_camera_mode and str(self.source_b_id) != str(self.source_a_id):
            self.cam_b = VideoSource(self.source_b_id, name="FonteB-Engajamento")
            self.cam_b.start()
        else:
            self.cam_b = None

    def get_frame_a(self) -> Optional[np.ndarray]:
        if self.cam_a:
            return self.cam_a.get_frame()
        return None

    def get_frame_b(self) -> Optional[np.ndarray]:
        # Se estiver em single camera mode ou Fonte B não iniciada, espelha o frame de A
        if self.single_camera_mode or self.cam_b is None:
            return self.get_frame_a()
        return self.cam_b.get_frame()

    def reconfigure(self, single_camera_mode: bool, source_a: Union[int, str], source_b: Union[int, str]):
        self.stop()
        self.single_camera_mode = single_camera_mode
        self.source_a_id = source_a
        self.source_b_id = source_b
        self._init_sources()

    def get_status(self) -> dict:
        return {
            "single_camera_mode": self.single_camera_mode,
            "source_a": self.source_a_id,
            "source_a_online": self.cam_a.is_alive() if self.cam_a else False,
            "source_b": self.source_b_id if not self.single_camera_mode else f"{self.source_a_id} (multiplexada)",
            "source_b_online": (self.cam_b.is_alive() if self.cam_b else (self.cam_a.is_alive() if self.cam_a else False))
        }

    def stop(self):
        if self.cam_a:
            self.cam_a.stop()
            self.cam_a = None
        if self.cam_b:
            self.cam_b.stop()
            self.cam_b = None


def test_camera_device(device_id: int) -> Tuple[bool, str]:
    """Testa se um índice de câmera responde com sucesso no Windows."""
    cap = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        return False, f"Não foi possível abrir o dispositivo {device_id}."
    
    ok, frame = cap.read()
    cap.release()
    if ok and frame is not None:
        h, w = frame.shape[:2]
        return True, f"Câmera {device_id} pronta ({w}x{h})."
    return False, f"Câmera {device_id} abriu, mas não entregou frames válidos."
