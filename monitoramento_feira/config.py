import os
import json
from dataclasses import dataclass, field, asdict
from typing import List, Union

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

@dataclass
class AppConfig:
    # Fontes de Câmera
    camera_a_source: Union[int, str] = 0
    camera_b_source: Union[int, str] = 1
    camera_a_enabled: bool = True
    camera_b_enabled: bool = True
    single_camera_mode: bool = True  # Quando ativo, multiplexa a webcam única (Fonte A) para ambos os pipelines

    # Dimensões e Homografia do Radar (espaço normalizado 0-1000)
    radar_dim: int = 1000
    inverter_eixo_x: bool = True       # Inverte eixo horizontal para corresponder ao espelhamento natural
    homografia_src_pts: List[List[float]] = field(default_factory=lambda: [
        [120.0, 150.0],
        [520.0, 150.0],
        [600.0, 450.0],
        [40.0, 450.0]
    ])
    homografia_dst_pts: List[List[float]] = field(default_factory=lambda: [
        [200.0, 200.0],
        [800.0, 200.0],
        [800.0, 800.0],
        [200.0, 800.0]
    ])
    # Zona de parada estrita em frente à bancada (base inferior Y >= 825)
    zona_poligono: List[List[float]] = field(default_factory=lambda: [
        [280.0, 825.0],
        [720.0, 825.0],
        [760.0, 995.0],
        [240.0, 995.0]
    ])

    # Parâmetros de Engajamento (tolerância natural para visão frontal)
    yaw_limiar: float = 35.0
    pitch_limiar: float = 35.0
    min_dwell_time: float = 3.0       # Sessões < 3s são descartadas como trânsito
    saturation_dwell_time: float = 30.0 # Teto para cálculo do score

    session_timeout: float = 2.0      # Tempo sem detecção para fechar sessão

    # Persistência e Portas
    db_path: str = os.path.join(os.path.dirname(__file__), "feira_monitoramento.db")
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    dashboard_port: int = 8501

    def save(self, path: str = CONFIG_PATH):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=4)

    @classmethod
    def load(cls, path: str = CONFIG_PATH) -> "AppConfig":
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return cls(**data)
            except Exception as e:
                print(f"[Config] Aviso ao carregar {path}: {e}. Usando configuração padrão.")
        cfg = cls()
        cfg.save(path)
        return cfg

# Instância global compartilhada
config = AppConfig.load()
