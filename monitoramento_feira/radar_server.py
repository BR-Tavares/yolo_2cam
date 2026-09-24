import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class HomografiaUpdate(BaseModel):
    src_pts: List[List[float]]
    dst_pts: Optional[List[List[float]]] = None

app = FastAPI(title="Radar & Engagement Server", version="1.0.0")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Referências injetadas pelo runner principal
trajectory_state = None
engagement_state = None
camera_manager = None
modelo_trajetoria = None
app_config = None
database = None

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

@app.get("/")
def index():
    return RedirectResponse(url="/radar")

@app.get("/radar", response_class=HTMLResponse)
def get_radar_page():
    path = os.path.join(STATIC_DIR, "radar.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Radar HTML não encontrado</h1>"

@app.get("/engajamento", response_class=HTMLResponse)
def get_engajamento_page():
    path = os.path.join(STATIC_DIR, "engajamento.html")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Engajamento HTML não encontrado</h1>"

@app.get("/api/radar")
def api_radar():
    if trajectory_state is None:
        return {"tracks": []}
    return {"tracks": trajectory_state.get_snapshot()}

@app.get("/api/engajamento")
def api_engajamento():
    if engagement_state is None:
        return {"active": False, "count": 0, "principal": None}
    return engagement_state.get_snapshot()

import cv2
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

# Variáveis globais para os frames anotados
last_frame_a = None
last_frame_b = None

@app.get("/api/status")
def api_status():
    cam_status = camera_manager.get_status() if camera_manager else {}
    tracks_count = len(trajectory_state.active) if trajectory_state else 0
    faces_count = len(engagement_state.active) if engagement_state else 0
    return {
        "status": "online",
        "cameras": cam_status,
        "active_tracks": tracks_count,
        "active_faces": faces_count
    }

@app.get("/api/preview_a")
def api_preview_a():
    global last_frame_a
    if last_frame_a is None:
        raise HTTPException(status_code=404, detail="Nenhum frame disponível ainda")
    ok, buf = cv2.imencode(".jpg", last_frame_a)
    if not ok:
        raise HTTPException(status_code=500, detail="Erro ao codificar frame")
    return Response(content=buf.tobytes(), media_type="image/jpeg")

@app.get("/api/preview_b")
def api_preview_b():
    global last_frame_b
    if last_frame_b is None:
        # Se for webcam única, retorna o preview de A
        if last_frame_a is not None:
            ok, buf = cv2.imencode(".jpg", last_frame_a)
            if ok:
                return Response(content=buf.tobytes(), media_type="image/jpeg")
        raise HTTPException(status_code=404, detail="Nenhum frame disponível ainda")
    ok, buf = cv2.imencode(".jpg", last_frame_b)
    if not ok:
        raise HTTPException(status_code=500, detail="Erro ao codificar frame")
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@app.post("/api/recalibrate")
def api_recalibrate(payload: Dict[str, Any]):
    global app_config, modelo_trajetoria
    src_pts = payload.get("src_pts")
    if not src_pts or len(src_pts) != 4:
        raise HTTPException(status_code=400, detail="Requer exatamente 4 pontos src_pts")

    if app_config:
        app_config.homografia_src_pts = src_pts
        app_config.save()

    if modelo_trajetoria:
        modelo_trajetoria.recalcular_geometria(
            src_pts=app_config.homografia_src_pts,
            dst_pts=app_config.homografia_dst_pts,
            zona_poligono=app_config.zona_poligono
        )
    return {"success": True, "src_pts": src_pts}

@app.post("/api/reset")
def api_reset():
    global trajectory_state, engagement_state
    if trajectory_state:
        with trajectory_state.lock:
            trajectory_state.active.clear()
    if engagement_state:
        with engagement_state.lock:
            engagement_state.active.clear()
    return {"success": True, "message": "Memória de rastreamento resetada com sucesso"}

@app.post("/api/consolidar")
def api_consolidar():
    global trajectory_state, engagement_state, database
    # 1. Força a sincronização imediata de quem está na câmera agora
    if trajectory_state and hasattr(trajectory_state, "sincronizar_ativos_agora"):
        trajectory_state.sincronizar_ativos_agora()
    if engagement_state and hasattr(engagement_state, "sincronizar_ativos_agora"):
        engagement_state.sincronizar_ativos_agora()

    # 2. Fecha e grava a janela estatística
    novo_id = None
    if database:
        novo_id = database.agregar_janela(janela_segundos=300.0)
    return {"success": True, "janela_id": novo_id}
