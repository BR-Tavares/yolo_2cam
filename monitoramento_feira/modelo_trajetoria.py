import cv2
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import os

class ModeloTrajetoria:
    """Modelo A — Detecção e Rastreamento de Pessoas com Projeção Homográfica para o Radar."""
    def __init__(self, src_pts: List[List[float]], dst_pts: List[List[float]], zona_poligono: List[List[float]], inverter_eixo_x: bool = True, model_name: str = "yolo11n.pt"):
        self.model_name = model_name
        self.inverter_eixo_x = inverter_eixo_x
        self.model = None
        self._carregar_modelo()

        self.src_pts = src_pts
        self.dst_pts = dst_pts
        self.zona_poligono = zona_poligono
        self.H = None
        self.zona_np = None
        self.recalcular_geometria(src_pts, dst_pts, zona_poligono)


    def _carregar_modelo(self):
        from ultralytics import YOLO
        try:
            self.model = YOLO(self.model_name)
            print(f"[ModeloTrajetoria] Carregado {self.model_name} com sucesso.")
        except Exception as e:
            fallback = "yolov8n.pt"
            print(f"[ModeloTrajetoria] Falha ao carregar {self.model_name}: {e}. Tentando fallback {fallback}...")
            self.model = YOLO(fallback)

    def recalcular_geometria(self, src_pts: List[List[float]], dst_pts: List[List[float]], zona_poligono: List[List[float]]):
        self.src_pts = src_pts
        self.dst_pts = dst_pts
        self.zona_poligono = zona_poligono

        src_arr = np.array(src_pts, dtype=np.float32)
        dst_arr = np.array(dst_pts, dtype=np.float32)
        self.H = cv2.getPerspectiveTransform(src_arr, dst_arr)
        self.zona_np = np.array(zona_poligono, dtype=np.int32)

    def processar(self, frame: np.ndarray, draw_overlay: bool = True) -> Tuple[List[Dict[str, Any]], np.ndarray]:
        if frame is None or self.model is None:
            return [], frame

        annotated = frame.copy() if draw_overlay else frame
        h, w = frame.shape[:2]

        # Tracking nativo ByteTrack (somente classe 0: person)
        results = self.model.track(
            frame,
            tracker="bytetrack.yaml",
            persist=True,
            classes=[0],
            verbose=False,
            imgsz=640
        )

        saida = []
        if not results or len(results) == 0 or results[0].boxes is None:
            return saida, annotated

        boxes = results[0].boxes
        for box in boxes:
            track_id = int(box.id[0]) if box.id is not None else None
            if track_id is None:
                continue

            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
            # Ponto médio dos pés da pessoa
            pe_x, pe_y = (x1 + x2) / 2.0, y2

            # Aplicação da Homografia para o espaço do Radar
            ponto_in = np.array([[[pe_x, pe_y]]], dtype=np.float32)
            ponto_out = cv2.perspectiveTransform(ponto_in, self.H)[0][0]
            rx, ry = float(ponto_out[0]), float(ponto_out[1])

            # Inversão do eixo horizontal (espelhamento natural direita-esquerda)
            if self.inverter_eixo_x:
                rx = 1000.0 - rx

            # Limitação ao espaço 0..1000
            rx_clamped = max(0.0, min(1000.0, rx))
            ry_clamped = max(0.0, min(1000.0, ry))

            # Teste de proximidade / polígono da zona do stand
            na_zona = cv2.pointPolygonTest(self.zona_np, (rx_clamped, ry_clamped), False) >= 0


            det = {
                "track_id": track_id,
                "bbox": [x1, y1, x2, y2],
                "pe": [pe_x, pe_y],
                "pos_radar": [rx_clamped, ry_clamped],
                "na_zona": bool(na_zona)
            }
            saida.append(det)

            if draw_overlay:
                cor = (0, 255, 120) if na_zona else (255, 200, 0)
                cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), cor, 2)
                cv2.circle(annotated, (int(pe_x), int(pe_y)), 5, (0, 0, 255), -1)
                status_txt = "[BANCADA]" if na_zona else "[TRANSITO]"
                cv2.putText(
                    annotated,
                    f"ID:{track_id} {status_txt}",
                    (int(x1), max(20, int(y1) - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, cor, 2
                )

        if draw_overlay:
            # Desenha os 4 pontos de ancoragem da calibração atual no frame
            pts = np.array(self.src_pts, dtype=np.int32)
            cv2.polylines(annotated, [pts], isClosed=True, color=(200, 50, 255), thickness=2)
            for idx, pt in enumerate(self.src_pts):
                cv2.circle(annotated, (int(pt[0]), int(pt[1])), 6, (0, 255, 255), -1)
                cv2.putText(annotated, f"P{idx+1}", (int(pt[0]) + 8, int(pt[1]) - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        return saida, annotated
