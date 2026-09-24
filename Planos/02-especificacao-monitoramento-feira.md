# Especificação de Projeto — Sistema de Monitoramento e Engajamento de Feira

**Status:** especificação de referência para implementação
**Público-alvo deste documento:** um agente/modelo de IA responsável pela implementação. Este documento é a fonte de verdade — qualquer decisão de design não coberta aqui deve ser resolvida seguindo os princípios da Seção 0, não por preferência arbitrária do implementador.

---

## 0. Princípios não-negociáveis (leia antes de tudo)

1. **Escala do problema:** um stand de feira, uma sessão de poucos dias, duas fontes de câmera, um único notebook (GPU RTX 4050, 6GB VRAM). Isto NÃO é um deploy de varejo multi-loja. Qualquer sugestão de infraestrutura pesada (DeepStream, OpenVINO, Kubernetes, message brokers distribuídos, bancos de dados gerenciados) deve ser rejeitada por padrão.
2. **Simplicidade defensável:** a escolha técnica default é sempre a mais simples que resolve o requisito. Otimização (quantização, streams CUDA paralelos, etc.) só é justificada depois de medir um gargalo real, nunca preventivamente.
3. **Privacidade por construção:** nenhum frame de vídeo bruto é persistido em disco, em nenhuma camada. Apenas vetores numéricos (posições, tempos, scores) são gravados.
4. **Duas câmeras, dois papéis, sem fusão de identidade:** a câmera elevada (trajetória/público) e a câmera do notebook (engajamento) são tratadas como **fontes de métricas independentes**. Não há tentativa de re-identificação cross-câmera (nada de histograma de cor, nada de embeddings de re-ID). Isso é uma decisão de design deliberada, não uma lacuna — evita um subsistema frágil e sem retorno proporcional ao esforço.
5. **Duas telas públicas com propósitos distintos:**
   - **Tela Radar:** visão ambiente, sempre ativa, mostra fluxo/trajetória de forma abstrata (estilo radar/cometa), alimentada exclusivamente pela câmera elevada.
   - **Tela(s) de Engajamento:** disparada por proximidade, mostra métrica pessoal da sessão atual de quem está perto, alimentada exclusivamente pela câmera do notebook.
   Essas duas telas NUNCA compartilham lógica de renderização nem tentam se sincronizar por identidade de pessoa.

### Lista explícita do que NÃO implementar nesta fase
- ❌ NVIDIA DeepStream ou Intel OpenVINO como framework de pipeline
- ❌ Quantização TensorRT/INT8 (só revisitar se FPS medido for insuficiente)
- ❌ Redis ou qualquer banco de dados externo — estado em memória (processo Python) é suficiente
- ❌ Re-identificação cross-câmera (histograma de cor, embeddings, biometria facial)
- ❌ CUDA streams manuais / paralelismo assíncrono customizado
- ❌ Qualquer modelo de reconhecimento facial (identificar *quem* é a pessoa) — o sistema é anônimo por design

Se o implementador considerar necessário desviar de qualquer item acima, deve primeiro justificar por escrito por que o requisito não pode ser satisfeito dentro dos limites da Seção 0, e não apenas substituir silenciosamente.

---

## 1. Objetivo do sistema

Monitorar, ao longo do tempo, a condição de público de um stand em feira: fluxo de pessoas (quantas, trajetória aproximada) e engajamento (quem se aproxima e por quanto tempo demonstra interesse), apresentando isso em duas camadas:
- uma **experiência visual pública de impacto** (telas voltadas ao público, esteticamente pensadas para encantar)
- um **painel analítico privado** para o organizador revisar depois

---

## 2. Hardware e fontes de vídeo

| Item | Especificação |
|---|---|
| Processamento | Notebook com GPU NVIDIA RTX 4050 (6GB VRAM) |
| Fonte A — Público/Trajetória | Webcam USB externa, montada em tripé elevado, conectada por cabo, posicionada para campo de visão amplo e ângulo descendente sobre a área do stand |
| Fonte B — Engajamento | Câmera embutida do notebook (ou webcam secundária), baixa, voltada para quem se aproxima do stand |

Ambas capturadas via OpenCV (`cv2.VideoCapture`), em threads separadas, sem dependência entre si — falha em uma fonte não deve derrubar a outra.

### 2.1 Flexibilidade de Câmeras e Configuração Dinâmica
- **Ambiente de Testes / Desenvolvimento:** deve permitir testar o sistema com apenas **1 única webcam conectada** (multiplexando a mesma câmera para os dois pipelines, ou ativando/alternando cada pipeline de forma independente para testes de validação).
- **Ambiente de Feira / Notebook:** o painel de controle (Dashboard) deve dispor de seleção direta de dispositivo (`0`, `1`, `2...` ou RTSP/HTTP URL) para cada uma das fontes (Fonte A - Público e Fonte B - Engajamento), permitindo configurar, testar o preview e iniciar/parar as câmeras individualmente sem necessidade de editar arquivos de configuração ou reiniciar o processo.


---

## 3. Arquitetura (visão geral)

```
[Webcam elevada] ──► [Modelo A: YOLO11n/YOLO26n + ByteTrack] ──► [Homografia] ──► [Estado: Trajetória] ──► [Tela Radar]
                                                                                          │
                                                                                          ▼
                                                                                   [SQLite: agregados]
                                                                                          ▲
                                                                                          │
[Câmera notebook] ──► [Modelo B: YOLO-face + landmarks] ──► [Pose de cabeça + dwell] ──► [Estado: Engajamento] ──► [Tela(s) de Engajamento]
                                                                                                                          │
                                                                                                                          ▼
                                                                                                              [Painel Analítico (Streamlit)]
```

---

## 4. Modelo A — Público / Trajetória

- **Modelo:** `YOLO11n` (padrão estável) ou `YOLO26n` (mais recente, ganhos de CPU/edge) via biblioteca `ultralytics`. Classe de interesse: `person`.
- **Tracking:** `model.track(source, tracker="bytetrack.yaml")` — ByteTrack embutido na própria Ultralytics, sem dependência externa adicional.
- **Frame rate de inferência:** 10–15 FPS é suficiente. Se a fonte entregar 30 FPS, aplicar frame skipping (processar 1 a cada 2–3 frames) e deixar o tracker interpolar a posição nos frames intermediários.
- **Resolução de entrada do modelo:** iniciar em 640×640 (padrão). Reduzir para 416×416 apenas se o teste de FPS mostrar necessidade — não antecipar essa otimização.
- **Saída por frame:** lista de `(track_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, timestamp)`.

### 4.1 Homografia (transformação para o plano do "radar")

1. **Calibração (etapa manual, uma vez por instalação física):** marcar 4 pontos de referência no chão real dentro do campo de visão da webcam elevada (ex: cantos de uma área demarcada). Registrar suas coordenadas de pixel na imagem e as coordenadas correspondentes no espaço abstrato do radar (ex: um quadrado normalizado 0–1000 × 0–1000).
2. Calcular a matriz de homografia com `cv2.getPerspectiveTransform` (4 pontos) ou `cv2.findHomography` (mais de 4 pontos, mais robusto a erro de marcação).
3. Para cada pessoa detectada, usar o **ponto médio da base do bounding box** (`((x1+x2)/2, y2)`) como proxy do ponto onde os pés tocam o chão, e aplicar `cv2.perspectiveTransform` para obter a posição estimada no espaço do radar.
4. **Resiliência a solavancos (Re-calibração Rápida):** o sistema deve salvar os pontos calibrados em JSON local e permitir reajustar visualmente os 4 pontos de ancoragem a qualquer momento via interface gráfica ou atalho de calibração, sem necessitar reiniciar o pipeline ou o processo principal.


### 4.2 Zona de engajamento / tripwire

- Definir um polígono no espaço do radar representando a área "próxima ao stand".
- Testar a cada frame se a posição transformada de um `track_id` está dentro do polígono (`cv2.pointPolygonTest`).
- Manter, por `track_id`: tempo de entrada na zona, tempo de saída, tempo acumulado dentro da zona.

---

## 5. Modelo B — Engajamento

- **Detecção e Rastreamento de rosto:** modelo YOLO especializado em face com landmarks (ex: linha `yolov8-face` / `yolov8n-face` ou modelo YOLO Pose adaptado), rodando sobre o feed da câmera do notebook. Saída: bounding box do rosto + pontos de referência (olhos, nariz, cantos da boca) + `track_id` persistente entre frames.
  - **Rastreamento Contínuo (Obrigatório):** para que `dwell_time` e `start_ts` funcionem corretamente, cada rosto detectado deve manter um `face_session_id` estável. Deve ser utilizado o rastreador nativo (`model.track(..., tracker="bytetrack.yaml", persist=True)`) ou um tracker leve por proximidade espacial (IoU/Centróide) caso o checkpoint específico de face opere apenas em modo detect.
- **Estimativa de orientação da cabeça (yaw/pitch via `cv2.solvePnP`):**
  - Utilizar os landmarks faciais contra um modelo 3D canônico de face.
  - **Correspondência de Índices de Landmarks:** a ordem dos pontos 2D retornados pelo modelo (ex: `results[0].keypoints`) deve corresponder rigorosamente à ordem dos `PONTOS_3D_CANONICOS` no código. O modelo típico de 5 landmarks fornece: `[0: olho_esq, 1: olho_dir, 2: nariz, 3: boca_esq, 4: boca_dir]`. A matriz 3D deve seguir essa exata mesma sequência para não gerar distorções de yaw/pitch.
- **Definição de engajamento (regra explícita, não ambígua):**
  - `dwell_time`: tempo contínuo que um mesmo rosto rastreado permanece detectado na cena.
  - `facing`: verdadeiro se `|yaw| < 25°` e `|pitch| < 20°` (a pessoa está aproximadamente de frente para a câmera/stand). Esses limiares são ponto de partida — ajustáveis empiricamente, mas devem existir como constantes nomeadas no código, nunca hardcoded soltos.
  - `engagement_score` (0 a 1): proporção do `dwell_time` em que `facing == true`, multiplicada por um fator de saturação em função do tempo total (ex: normalizar por um teto de 30s — depois disso o score não cresce mais, evita outlier dominar o dashboard).
- **Threshold de ruído:** ignorar qualquer sessão de rosto com `dwell_time < 3s` — não conta como engajamento, é trânsito.

> Nota: como Modelo A e Modelo B não compartilham identidade (Seção 0, item 4), o "engajamento" registrado é sempre relativo a quem está diante da câmera do notebook, e é tratado como evento próprio — não é somado ao histórico de trajetória de uma pessoa específica do radar.


---

## 6. Camada de Estado (processo Python, em memória)

Duas estruturas de estado independentes, cada uma um dicionário `id → objeto de estado`, geridas por thread própria:

```python
class TrajectoryState:
    def __init__(self):
        self.active = {}  # track_id -> {"trail": [...], "zone_enter_ts": float|None, "zone_time_total": float}

class EngagementState:
    def __init__(self):
        self.active = {}  # face_session_id -> {"start_ts": float, "facing_time": float, "last_seen": float}
```

Sessões expiram (são removidas de `active` e fechadas/persistidas) quando não há atualização por N segundos (sugestão: 2s), indicando que a pessoa saiu de cena.

---

## 7. Persistência (SQLite)

Nenhum frame é salvo. Apenas os seguintes registros, ao fechar cada sessão:

```sql
CREATE TABLE sessoes_trajetoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    inicio_ts REAL,
    fim_ts REAL,
    tempo_na_zona REAL
);

CREATE TABLE sessoes_engajamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id TEXT,
    inicio_ts REAL,
    fim_ts REAL,
    dwell_time REAL,
    facing_time REAL,
    engagement_score REAL
);

CREATE TABLE agregados_janela (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    janela_inicio REAL,
    janela_fim REAL,
    visitantes_unicos INTEGER,
    tempo_medio_zona REAL,
    engajamentos_validos INTEGER,
    score_medio REAL
);
```

Um processo agregador roda a cada N minutos (sugestão: 5) consolidando as tabelas de sessão em `agregados_janela`.

---

## 8. Apresentação

### 8.1 Tela Radar (pública, ambiente, sempre ativa)
- Fundo escuro, grade circular concêntrica, stand no centro.
- Cada `track_id` ativo em `TrajectoryState` vira um ponto com cauda (rastro tipo cometa), posição = coordenada homografada.
- Fonte de dados: leitura periódica em alta frequência (polling curto de 200–500ms ou SSE - Server-Sent Events via endpoint local FastAPI/Flask) para garantir fluidez do rastro cometa sem engasgos visuais.
- Renderização: HTML5/Canvas (arquivo único standalone, sem dependências pesadas, executável diretamente no navegador).

### 8.2 Tela(s) de Engajamento (disparada por proximidade)
- Troca de conteúdo disparada quando uma sessão de engajamento está ativa (`EngagementState.active` não-vazio).
- Mostra: tempo de permanência atual, indicador visual de "energia"/score — sem texto técnico, sem número cru de coordenadas.
- Atualização em tempo real (200–500ms via polling ou SSE).

### 8.3 Painel de Controle e Analítico (privado, Streamlit)
- **Aba de Controle de Fontes de Vídeo:**
  - Configuração dinâmica das câmeras (Fonte A: Público e Fonte B: Engajamento) via seletor de índice (`0`, `1`, `2...`) ou URL de stream.
  - Modo flexível: permite rodar em modo teste com 1 única webcam (multiplexando ou isolando uma fonte) ou ativar 2 câmeras físicas simultâneas no notebook.
  - Preview visual ao vivo de cada câmera com overlay de detecções e bounding boxes.
  - Interface para recalibração dos 4 pontos de homografia com salvamento imediato em JSON.
- **Aba Analítica:**
  - Lê `agregados_janela` e as tabelas de sessão do SQLite.
  - Gráficos mínimos: fluxo de visitantes ao longo do tempo, tempo médio de permanência na zona, distribuição de `engagement_score`, comparação por hora do dia.


---

## 9. Fases de implementação (ordem obrigatória)

1. Captura + Modelo A isolado, validar FPS real e desenho do polígono de zona.
2. Homografia calibrada com pontos reais do ambiente da feira → Tela Radar funcional com dados reais de trajetória (sem engajamento ainda).
3. Modelo B isolado (detecção de rosto + pose de cabeça + regra de engajamento) → validar `engagement_score` com testes manuais antes de plugar na tela.
4. Persistência SQLite + agregador de janela.
5. Painel analítico Streamlit.
6. Polimento visual das telas públicas (Radar e Engajamento).

Nenhuma fase deve pular para otimização de performance (Seção 0, item 2) antes de medir que ela é necessária.

---

## 10. Esqueleto de código de partida

```python
# captura.py
import cv2
import threading
import time

class VideoSource:
    def __init__(self, source_id, name):
        self.cap = cv2.VideoCapture(source_id)
        self.name = name
        self.latest_frame = None
        self.lock = threading.Lock()
        self.running = True

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if ok:
                with self.lock:
                    self.latest_frame = frame
            else:
                time.sleep(0.05)

    def get_frame(self):
        with self.lock:
            return None if self.latest_frame is None else self.latest_frame.copy()
```

```python
# modelo_trajetoria.py
from ultralytics import YOLO
import cv2
import numpy as np

class ModeloTrajetoria:
    def __init__(self, homografia_matrix, zona_poligono):
        self.model = YOLO("yolo11n.pt")
        self.H = homografia_matrix
        self.zona = np.array(zona_poligono, dtype=np.int32)

    def processar(self, frame):
        results = self.model.track(frame, tracker="bytetrack.yaml", persist=True, classes=[0], verbose=False)
        saida = []
        for box in results[0].boxes:
            track_id = int(box.id[0]) if box.id is not None else None
            if track_id is None:
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            pe_x, pe_y = (x1 + x2) / 2, y2
            ponto_radar = cv2.perspectiveTransform(
                np.array([[[pe_x, pe_y]]], dtype=np.float32), self.H
            )[0][0]
            na_zona = cv2.pointPolygonTest(self.zona, tuple(ponto_radar), False) >= 0
            saida.append({"track_id": track_id, "pos_radar": ponto_radar.tolist(), "na_zona": bool(na_zona)})
        return saida
```

```python
# modelo_engajamento.py
# Requer um modelo yolo-face com landmarks (ex: yolov8n-face / yolov8-pose) e pontos 3D canônicos.
import cv2
import numpy as np
from ultralytics import YOLO

# Ordem correspondente aos landmarks típicos de face (olho_esq, olho_dir, nariz, boca_esq, boca_dir):
PONTOS_3D_CANONICOS = np.array([
    [-30.0, -30.0, -30.0], # olho esquerdo
    [30.0, -30.0, -30.0],  # olho direito
    [0.0, 0.0, 0.0],       # nariz
    [-25.0, 30.0, -30.0],  # canto boca esquerdo
    [25.0, 30.0, -30.0],   # canto boca direito
], dtype=np.float64)

YAW_LIMIAR = 25.0
PITCH_LIMIAR = 20.0

class ModeloEngajamento:
    def __init__(self, camera_matrix):
        # yolov8n-face ou yolov8n-pose
        self.model = YOLO("yolov8n-face.pt")
        self.camera_matrix = camera_matrix
        self.dist_coeffs = np.zeros((4, 1))

    def processar(self, frame):
        # Utiliza tracker para persistir face_session_id entre frames
        results = self.model.track(frame, tracker="bytetrack.yaml", persist=True, verbose=False)[0]
        saida = []
        if results.boxes is None or results.keypoints is None:
            return saida

        for i, box in enumerate(results.boxes):
            track_id = int(box.id[0]) if box.id is not None else f"face_{i}"
            # Extração dos keypoints correspondentes à detecção i
            kpts = results.keypoints.xy[i].cpu().numpy()
            if len(kpts) < 5:
                continue
            pontos_2d = np.array(kpts[:5], dtype=np.float64)
            ok, rvec, _ = cv2.solvePnP(
                PONTOS_3D_CANONICOS, pontos_2d,
                self.camera_matrix, self.dist_coeffs
            )
            if not ok:
                continue
            rot_matrix, _ = cv2.Rodrigues(rvec)
            yaw = np.degrees(np.arctan2(rot_matrix[2, 0], rot_matrix[0, 0]))
            pitch = np.degrees(np.arctan2(-rot_matrix[2, 1], rot_matrix[2, 2]))
            facing = abs(yaw) < YAW_LIMIAR and abs(pitch) < PITCH_LIMIAR
            saida.append({
                "face_id": track_id,
                "facing": facing,
                "yaw": float(yaw),
                "pitch": float(pitch),
                "bbox": box.xyxy[0].tolist()
            })
        return saida
```

Estes arquivos compõem o esqueleto de partida. O pipeline de implementação cuidará da tolerância a falhas na captura, calibração dinâmica e suporte a multiplexação/troca de câmeras.

---

## 11. Critérios de aceite

- [ ] Nenhum frame de vídeo é gravado em disco em nenhum momento
- [ ] As duas câmeras operam de forma independente; falha em uma não derruba a outra
- [ ] O sistema permite rodar com 1 única câmera em ambiente de teste local e com 2 câmeras físicas no notebook da feira
- [ ] As fontes de vídeo (câmera A e câmera B) podem ser alteradas e testadas diretamente no dashboard sem modificar código
- [ ] Tela Radar atualiza com fluidez (<= 500ms) sem travamentos visuais
- [ ] Sessões de engajamento com `dwell_time < 3s` não aparecem em nenhuma métrica agregada
- [ ] Nenhuma dependência de infraestrutura externa (Redis, DeepStream, OpenVINO, bancos gerenciados) foi introduzida
- [ ] Nenhuma tentativa de vincular identidade entre as duas câmeras foi implementada
- [ ] O painel analítico lê exclusivamente do SQLite, nunca do estado em memória em tempo real

