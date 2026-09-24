import cv2
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
import math

# Pontos 3D canônicos calibrados para os 5 keypoints faciais do COCO Pose:
# 0: Nariz, 1: Olho Esq (no lado direito da imagem), 2: Olho Dir (no lado esquerdo da imagem), 3: Orelha Esq, 4: Orelha Dir
PONTOS_3D_COCO_FACIAIS = np.array([
    [0.0, 0.0, 0.0],        # 0: Nariz
    [30.0, -25.0, 20.0],    # 1: Olho Esquerdo (lado direito da imagem)
    [-30.0, -25.0, 20.0],   # 2: Olho Direito (lado esquerdo da imagem)
    [65.0, -15.0, 60.0],    # 3: Orelha Esquerda
    [-65.0, -15.0, 60.0]    # 4: Orelha Direita
], dtype=np.float64)

class ModeloEngajamento:
    """Modelo B — Detecção de Rosto/Pose, Rastreamento e Orientação de Cabeça (Yaw/Pitch via solvePnP)."""
    def __init__(self, yaw_limiar: float = 35.0, pitch_limiar: float = 35.0, model_name: str = "yolov8n-pose.pt"):
        self.yaw_limiar = yaw_limiar
        self.pitch_limiar = pitch_limiar
        self.model_name = model_name
        self.model = None
        self._carregar_modelo()

    def _carregar_modelo(self):
        from ultralytics import YOLO
        try:
            self.model = YOLO(self.model_name)
            print(f"[ModeloEngajamento] Carregado {self.model_name} com sucesso.")
        except Exception as e:
            fallback = "yolo11n-pose.pt"
            print(f"[ModeloEngajamento] Tentando modelo alternativo: {fallback}...")
            self.model = YOLO(fallback)

    def _estimar_pose_cabeca(self, kpts: np.ndarray, img_w: int, img_h: int) -> Tuple[bool, float, float]:
        """Aplica solvePnP (SQPNP) com subset de pontos válidos e validação geométrica de simetria (olhos e ombros)."""
        focal_length = float(img_w)
        center = (float(img_w) / 2.0, float(img_h) / 2.0)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype=np.float64)
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        pnp_facing = False
        yaw_deg, pitch_deg = 0.0, 0.0

        # 1. PnP 3D com pontos faciais válidos (OpenCV SQPNP suporta >= 3 pontos)
        valid_idx = [i for i in range(min(5, len(kpts))) if kpts[i][0] > 1.0 and kpts[i][1] > 1.0]
        if len(valid_idx) >= 3:
            try:
                pts_3d_subset = PONTOS_3D_COCO_FACIAIS[valid_idx]
                pts_2d_subset = kpts[valid_idx].astype(np.float64)
                ok, rvec, _ = cv2.solvePnP(
                    pts_3d_subset,
                    pts_2d_subset,
                    camera_matrix,
                    dist_coeffs,
                    flags=cv2.SOLVEPNP_SQPNP
                )
                if ok:
                    rot_matrix, _ = cv2.Rodrigues(rvec)
                    angles, _, _, _, _, _ = cv2.RQDecomp3x3(rot_matrix)
                    pitch_deg = float(angles[0])
                    yaw_deg = float(angles[1])
                    pnp_facing = (abs(yaw_deg) < self.yaw_limiar) and (abs(pitch_deg) < self.pitch_limiar)
            except Exception:
                pass

        # 2. Simetria facial (Nariz centralizado entre os olhos)
        geom_facial = False
        if len(kpts) >= 3 and kpts[0][0] > 1.0 and kpts[1][0] > 1.0 and kpts[2][0] > 1.0:
            nx, elx, erx = kpts[0][0], kpts[1][0], kpts[2][0]
            min_x, max_x = min(elx, erx), max(elx, erx)
            margem = (max_x - min_x) * 0.3
            if (min_x - margem) <= nx <= (max_x + margem):
                dl = abs(nx - elx)
                dr = abs(nx - erx)
                sim = min(dl, dr) / (max(dl, dr) + 1e-4)
                geom_facial = (sim >= 0.20)

        # 3. Simetria corporal (Nariz centralizado entre os ombros - funciona a média e longa distância!)
        geom_body = False
        if len(kpts) >= 7 and kpts[0][0] > 1.0 and kpts[5][0] > 1.0 and kpts[6][0] > 1.0:
            nx, lsx, rsx = kpts[0][0], kpts[5][0], kpts[6][0]
            largura_ombros = abs(lsx - rsx)
            if largura_ombros >= 25.0:
                min_s, max_s = min(lsx, rsx), max(lsx, rsx)
                if (min_s - 10) <= nx <= (max_s + 10):
                    dl_s = abs(nx - lsx)
                    dr_s = abs(nx - rsx)
                    sim_s = min(dl_s, dr_s) / (max(dl_s, dr_s) + 1e-4)
                    geom_body = (sim_s >= 0.20)

        facing = bool(pnp_facing or geom_facial or geom_body)
        return facing, yaw_deg, pitch_deg

    def processar(self, frame: np.ndarray, draw_overlay: bool = True) -> Tuple[List[Dict[str, Any]], np.ndarray]:
        if frame is None or self.model is None:
            return [], frame

        annotated = frame.copy() if draw_overlay else frame
        h, w = frame.shape[:2]

        results = self.model.track(
            frame,
            tracker="bytetrack.yaml",
            persist=True,
            verbose=False,
            imgsz=640
        )

        saida = []
        if not results or len(results) == 0:
            return saida, annotated

        res = results[0]
        if res.boxes is None or res.keypoints is None:
            return saida, annotated

        boxes = res.boxes
        kpts_all = res.keypoints.xy.cpu().numpy()

        for i, box in enumerate(boxes):
            track_id = int(box.id[0]) if (box.id is not None and len(box.id) > 0) else i
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()

            if i >= len(kpts_all):
                continue
            kpts = kpts_all[i]
            if len(kpts) < 3:
                continue

            pontos_faciais_2d = kpts[:min(5, len(kpts))]
            facing, yaw, pitch = self._estimar_pose_cabeca(kpts, w, h)

            saida.append({
                "face_id": f"person_{track_id}",
                "facing": facing,
                "yaw": yaw,
                "pitch": pitch,
                "bbox": [x1, y1, x2, y2]
            })

            if draw_overlay:
                cor = (0, 255, 0) if facing else (0, 165, 255)
                # Bounding box
                cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), cor, 2)
                # Desenha os pontos dos olhos e nariz
                for pt in pontos_faciais_2d:
                    if pt[0] > 0 and pt[1] > 0:
                        cv2.circle(annotated, (int(pt[0]), int(pt[1])), 4, (255, 255, 0), -1)

                status_txt = f"{'OLHANDO STAND' if facing else 'DESVIADO'} (Yaw: {yaw:.0f}°, Pitch: {pitch:.0f}°)"
                cv2.putText(
                    annotated,
                    f"ID:{track_id} - {status_txt}",
                    (int(x1), max(25, int(y1) - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 2
                )

        return saida, annotated
