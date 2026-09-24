# **Objetivo**

Construir uma demonstração local para feira empresarial em que uma webcam observa o ambiente, YOLO detecta/rastreia pessoas, uma camada determinística converte os tracks em um **estado semântico temporal**, e o Jev transforma esse estado em **julgamentos probabilísticos estratégicos** exibidos em séries temporais.

O vídeo deve permanecer local. Apenas o estado semântico deve ser enviado ao Jev.

---

# **Arquitetura alvo**

Webcam USB

&nbsp;&nbsp;&nbsp;↓

YOLO11 / TensorRT

&nbsp;&nbsp;&nbsp;↓

Multi-object tracking

&nbsp;&nbsp;&nbsp;↓

Spatial \+ Temporal Analytics

&nbsp;&nbsp;&nbsp;↓

Scene State Builder

&nbsp;&nbsp;&nbsp;↓

Jev API

&nbsp;&nbsp;&nbsp;↓

Time-series store

&nbsp;&nbsp;&nbsp;↓

Dashboard local

---

# **Stack**

## **Base de visão**

Usar:

* Python 3.11+  
* NVIDIA GPU  
* CUDA/TensorRT  
* NVIDIA DeepStream 9.1  
* Ultralytics YOLO11  
* OpenCV apenas para utilidades auxiliares

Repositórios:

* `https://github.com/NVIDIA/DeepStream`  
* `https://github.com/ultralytics/ultralytics`

O repositório oficial NVIDIA DeepStream contém atualmente o SDK 9.1 e aplicações de referência para pipelines GStreamer/TensorRT/tracking.

YOLO11 deve vir do repositório canônico `ultralytics/ultralytics`; o repo `ultralytics/yolo11` é apenas uma página de descoberta.

---

# **Hardware alvo**

Referência mínima recomendada:

Notebook

CPU: Intel i5/i7 ou Ryzen 5/7 recente

RAM: 16 GB

GPU: NVIDIA RTX 4050 6 GB ou superior

SSD: 512 GB+

Webcam: USB 1080p / 30 fps

Monitor externo: Full HD

Para uma câmera e YOLO11n/YOLO11s, não otimizar prematuramente para throughput extremo.

Meta inicial:

input: 1080p

inferência: 10–15 FPS

dashboard: 2–5 atualizações/s

Jev: 1 avaliação a cada 5–15 s

---

# **Fase 1 — Captura e detecção**

Implementar webcam USB como fonte.

Usar inicialmente:

YOLO11n

classe: person

imgsz: 640

confidence threshold: \~0.4

Depois exportar para TensorRT.

A saída mínima por detecção deve ser:

{

&nbsp;&nbsp;"timestamp": 1727010000.123,

&nbsp;&nbsp;"class": "person",

&nbsp;&nbsp;"confidence": 0.94,

&nbsp;&nbsp;"bbox": \[412, 188, 530, 604\]

}

---

# **Fase 2 — Tracking**

Acoplar tracking multiobjeto.

Preferência:

DeepStream nvtracker

Cada pessoa precisa receber um `track_id` temporário.

Contrato:

{

&nbsp;&nbsp;"timestamp": 1727010000.123,

&nbsp;&nbsp;"track\_id": 17,

&nbsp;&nbsp;"bbox": \[412, 188, 530, 604\],

&nbsp;&nbsp;"centroid": \[471, 396\],

&nbsp;&nbsp;"confidence": 0.94

}

O ID não representa identidade real e não deve persistir após a sessão.

---

# **Fase 3 — Histórico temporal**

Criar um buffer circular por `track_id`.

Manter aproximadamente:

60–120 segundos

Estrutura sugerida:

tracks \= {

&nbsp;&nbsp;&nbsp;&nbsp;track\_id: deque(\[

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"timestamp": ...,

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"x": ...,

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"y": ...,

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"bbox": ...

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;}

&nbsp;&nbsp;&nbsp;&nbsp;\])

}

Remover tracks expirados.

---

# **Fase 4 — Spatial/Temporal Analytics**

Criar um módulo:

analytics/

&nbsp;&nbsp;&nbsp;&nbsp;motion.py

&nbsp;&nbsp;&nbsp;&nbsp;groups.py

&nbsp;&nbsp;&nbsp;&nbsp;zones.py

&nbsp;&nbsp;&nbsp;&nbsp;flow.py

&nbsp;&nbsp;&nbsp;&nbsp;dwell.py

&nbsp;&nbsp;&nbsp;&nbsp;density.py

Não usar IA generativa nesta camada.

Tudo deve ser determinístico.

Calcular inicialmente:

### **Por pessoa**

velocity

direction

stationary\_duration

dwell\_time

current\_zone

trajectory\_length

### **Por grupo**

Criar agrupamento usando distância espacial entre centroids.

Começar com DBSCAN ou regra equivalente.

Gerar:

group\_count

largest\_group\_size

stationary\_group\_count

mean\_group\_duration

### **Por área**

Gerar:

people\_count

occupancy

density

mean\_velocity

stationary\_ratio

mean\_dwell

direction\_distribution

bidirectional\_flow

### **Tendências**

Comparar janelas:

últimos 30 s

versus

30 s anteriores

Gerar:

occupancy\_delta

density\_delta

velocity\_delta

stationary\_ratio\_delta

---

# **Fase 5 — ROIs**

Permitir configuração manual de polígonos.

Arquivo:

zones:

&nbsp;&nbsp;\- id: corridor

&nbsp;&nbsp;&nbsp;&nbsp;polygon:

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;\- \[100,100\]

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;\- \[900,100\]

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;\- \[900,600\]

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;\- \[100,600\]

&nbsp;

&nbsp;&nbsp;\- id: booth\_front

&nbsp;&nbsp;&nbsp;&nbsp;polygon:

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;\- \[...\]

Usar DeepStream `nvdsanalytics` quando conveniente para:

ROI

line crossing

direction

occupancy

Mas o Scene State Builder deve ser desacoplado do DeepStream para facilitar testes.

---

# **Fase 6 — Scene State Builder**

Esse é o componente central.

Criar:

scene\_state/

&nbsp;&nbsp;&nbsp;&nbsp;builder.py

&nbsp;&nbsp;&nbsp;&nbsp;schema.py

&nbsp;&nbsp;&nbsp;&nbsp;semantic\_rules.py

Entrada:

tracks \+ analytics atuais \+ histórico recente

Saída:

{

&nbsp;&nbsp;"timestamp": "2026-09-22T14:35:10-03:00",

&nbsp;&nbsp;"observation\_window\_seconds": 60,

&nbsp;

&nbsp;&nbsp;"scene": {

&nbsp;&nbsp;&nbsp;&nbsp;"people\_count": 23,

&nbsp;&nbsp;&nbsp;&nbsp;"group\_count": 4,

&nbsp;&nbsp;&nbsp;&nbsp;"largest\_group": 8

&nbsp;&nbsp;},

&nbsp;

&nbsp;&nbsp;"movement": {

&nbsp;&nbsp;&nbsp;&nbsp;"mean\_velocity": 0.42,

&nbsp;&nbsp;&nbsp;&nbsp;"stationary\_ratio": 0.61,

&nbsp;&nbsp;&nbsp;&nbsp;"bidirectional\_flow": true

&nbsp;&nbsp;},

&nbsp;

&nbsp;&nbsp;"persistence": {

&nbsp;&nbsp;&nbsp;&nbsp;"mean\_dwell\_seconds": 92,

&nbsp;&nbsp;&nbsp;&nbsp;"stationary\_groups": 2

&nbsp;&nbsp;},

&nbsp;

&nbsp;&nbsp;"trend": {

&nbsp;&nbsp;&nbsp;&nbsp;"people\_count\_change\_pct": 31,

&nbsp;&nbsp;&nbsp;&nbsp;"density\_trend": "increasing",

&nbsp;&nbsp;&nbsp;&nbsp;"mean\_velocity\_trend": "decreasing"

&nbsp;&nbsp;},

&nbsp;

&nbsp;&nbsp;"spatial": {

&nbsp;&nbsp;&nbsp;&nbsp;"corridor\_occupancy": 14,

&nbsp;&nbsp;&nbsp;&nbsp;"booth\_front\_occupancy": 9

&nbsp;&nbsp;},

&nbsp;

&nbsp;&nbsp;"semantic\_events": \[

&nbsp;&nbsp;&nbsp;&nbsp;"local\_density\_increasing",

&nbsp;&nbsp;&nbsp;&nbsp;"stationary\_group\_persistent",

&nbsp;&nbsp;&nbsp;&nbsp;"bidirectional\_flow\_present",

&nbsp;&nbsp;&nbsp;&nbsp;"movement\_speed\_decreasing"

&nbsp;&nbsp;\]

}

---

# **Fase 7 — Semântica determinística**

Não pedir ao Jev para descobrir fatos básicos que podem ser calculados.

Criar regras transparentes.

Exemplo:

if density\_delta \> threshold:

&nbsp;&nbsp;&nbsp;&nbsp;events.append("local\_density\_increasing")

&nbsp;

if stationary\_ratio \> threshold:

&nbsp;&nbsp;&nbsp;&nbsp;events.append("high\_stationary\_ratio")

&nbsp;

if stationary\_group\_count \>= 2:

&nbsp;&nbsp;&nbsp;&nbsp;events.append("multiple\_stationary\_groups")

&nbsp;

if bidirectional\_flow:

&nbsp;&nbsp;&nbsp;&nbsp;events.append("bidirectional\_flow\_present")

Os thresholds devem ficar em configuração, não hardcoded.

---

# **Fase 8 — Estado textual opcional**

Além do JSON, gerar uma representação textual previsível por template.

Não usar LLM.

Exemplo:

Observation window: 60 seconds.

There are currently 23 people in the monitored area.

Four groups are present; the largest contains eight people.

Two groups have remained stationary.

Person density increased by 31% compared with the previous interval.

Mean movement speed is decreasing.

Bidirectional flow is present.

The proportion of stationary people is 61%.

Esse texto pode ser incluído no `state` enviado ao Jev, junto com o JSON se necessário.

---

# **Fase 9 — Jev**

Usar a API oficial:

POST https://api.typesafe.ai/v1/systemone

A API expõe `Choice`, `Score` e `Noul` e recebe um `state` associado às perguntas estruturadas.

A chave deve vir de:

JEV\_API\_KEY

Nunca colocar chave no front-end.

Criar:

jev/

&nbsp;&nbsp;&nbsp;&nbsp;client.py

&nbsp;&nbsp;&nbsp;&nbsp;questions.py

&nbsp;&nbsp;&nbsp;&nbsp;schemas.py

---

# **Perguntas iniciais**

Manter poucas perguntas e semanticamente fortes.

Exemplo:

{

&nbsp;&nbsp;"state": "...scene state...",

&nbsp;&nbsp;"questions": {

&nbsp;&nbsp;&nbsp;&nbsp;"queue\_emerging": {

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "noul"

&nbsp;&nbsp;&nbsp;&nbsp;},

&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;"flow\_obstruction\_risk": {

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "noul"

&nbsp;&nbsp;&nbsp;&nbsp;},

&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;"commercial\_engagement\_opportunity": {

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "noul"

&nbsp;&nbsp;&nbsp;&nbsp;},

&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;"self\_dispersal\_likely": {

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "noul"

&nbsp;&nbsp;&nbsp;&nbsp;},

&nbsp;

&nbsp;&nbsp;&nbsp;&nbsp;"operational\_state": {

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"type": "choice",

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"options": \[

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"normal",

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"attention",

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"intervention"

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;\]

&nbsp;&nbsp;&nbsp;&nbsp;}

&nbsp;&nbsp;}

}

Não formular perguntas médicas ou diagnósticas.

---

# **Fase 10 — Time series**

Registrar cada avaliação.

Estrutura:

{

&nbsp;&nbsp;"timestamp": "...",

&nbsp;&nbsp;"question": "flow\_obstruction\_risk",

&nbsp;&nbsp;"probability": 0.73

}

Começar com SQLite.

Tabelas:

scene\_state

jev\_assessment

events

Não instalar banco distribuído para o MVP.

---

# **Fase 11 — Dashboard**

Usar:

FastAPI

\+

WebSocket

\+

React ou HTML/JS simples

\+

Plotly/ECharts

Manter local:

http://localhost:8000

Layout:

┌───────────────────────────────────────┐

│ LIVE SITUATIONAL AWARENESS     14:42 │

├───────────────────────────────────────┤

│ PEOPLE  │ GROUPS │ DWELL │ MOVEMENT  │

├───────────────────────────────────────┤

│                                       │

│         HEATMAP / LIVE MAP            │

│                                       │

├───────────────────────────────────────┤

│ AI JUDGEMENTS                         │

│                                       │

│ Obstruction risk      ─────────── 73% │

│ Queue emerging        ────────    58% │

│ Commercial opportunity ───────── 81% │

│ Self-dispersal        ─────       32% │

├───────────────────────────────────────┤

│ TIME SERIES — LAST 20 MIN             │

│        ╭───────╮                      │

│  ─────╯       ╰────                  │

└───────────────────────────────────────┘

A visualização principal deve ser a evolução temporal das perguntas do Jev.

---

# **Fase 12 — Heatmap**

Gerar localmente.

Usar coordenadas dos centroids acumuladas no tempo.

Dois modos:

presence heatmap

dwell heatmap

O segundo é prioritário.

Não armazenar frames para gerar heatmap.

---

# **Estrutura sugerida do projeto**

situational-awareness/

│

├── README.md

├── pyproject.toml

├── .env.example

│

├── config/

│   ├── camera.yaml

│   ├── zones.yaml

│   ├── analytics.yaml

│   └── questions.yaml

│

├── vision/

│   ├── detector.py

│   ├── tracker.py

│   └── pipeline.py

│

├── analytics/

│   ├── motion.py

│   ├── groups.py

│   ├── dwell.py

│   ├── density.py

│   ├── flow.py

│   └── zones.py

│

├── scene\_state/

│   ├── schema.py

│   ├── builder.py

│   └── semantic\_rules.py

│

├── jev/

│   ├── client.py

│   ├── schemas.py

│   └── questions.py

│

├── storage/

│   ├── db.py

│   └── models.py

│

├── api/

│   ├── main.py

│   └── websocket.py

│

├── dashboard/

│   └── ...

│

└── tests/

&nbsp;&nbsp;&nbsp;&nbsp;├── test\_tracking.py

&nbsp;&nbsp;&nbsp;&nbsp;├── test\_analytics.py

&nbsp;&nbsp;&nbsp;&nbsp;├── test\_scene\_state.py

&nbsp;&nbsp;&nbsp;&nbsp;└── fixtures/

---

# **Ordem obrigatória de implementação**

Não desenvolver tudo simultaneamente.

## **Milestone 1**

webcam → YOLO → bounding boxes

Aceite:

* webcam estável por 30 min;  
* apenas classe person;  
* FPS exibido.

## **Milestone 2**

YOLO → tracking

Aceite:

* track IDs visualizados;  
* IDs razoavelmente persistentes.

## **Milestone 3**

tracking → analytics

Aceite:

* occupancy;  
* velocity;  
* dwell;  
* stationary ratio;  
* groups.

## **Milestone 4**

analytics → scene state

Aceite:

* JSON atualizado a cada 5 s;  
* JSON validado contra schema;  
* nenhum campo depende de LLM.

## **Milestone 5**

scene state → Jev

Aceite:

* request válido;  
* respostas estruturadas;  
* retry/backoff;  
* funcionamento degradado quando sem internet.

## **Milestone 6**

Jev → time series

Aceite:

* histórico armazenado;  
* probabilidades recuperáveis por intervalo.

## **Milestone 7**

dashboard

Aceite:

* atualização em tempo real;  
* heatmap;  
* estado observado;  
* séries temporais das perguntas.

## **Milestone 8**

TensorRT

Somente depois de tudo funcionar.

Exportar YOLO para TensorRT e substituir inferência PyTorch.

---

# **Funcionamento sem internet**

A aplicação deve continuar funcionando sem acesso ao Jev.

Nesse caso:

YOLO       OK

tracking   OK

analytics  OK

heatmap    OK

dashboard  OK

Jev        OFFLINE

O dashboard deve mostrar:

Decision model unavailable — local monitoring active

Nunca travar o pipeline de visão porque a API está indisponível.

---

# **Privacidade**

Não implementar:

face recognition

identity matching

gender inference

race inference

personal identification

cross-session identification

Não armazenar vídeo por padrão.

Armazenar:

anonymous track IDs

aggregated measurements

scene states

Jev responses

timestamps

---

# **Critérios de sucesso do MVP**

O sistema está pronto para demonstração quando:

1. Funciona por pelo menos 1 hora contínua.  
2. Webcam e dashboard funcionam sem internet.  
3. Pessoas são rastreadas anonimamente.  
4. Heatmap responde visualmente ao comportamento observado.  
5. Scene State muda coerentemente com alterações reais da cena.  
6. Jev recebe apenas metadata/estado, nunca vídeo.  
7. As probabilidades do Jev ficam armazenadas como séries temporais.  
8. Uma pessoa olhando a tela entende em menos de 10 segundos que:  
   * a máquina observa o ambiente;  
   * constrói um estado;  
   * formula julgamentos;  
   * esses julgamentos evoluem conforme a situação muda.

---

# **Regra de engenharia**

Não adicionar outra IA, VLM, LLM, banco distribuído, cloud pipeline ou arquitetura multiagente sem necessidade demonstrada.

Para o MVP:

YOLO \+ tracking

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓

analytics determinístico

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓

Scene State

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓

Jev

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓

dashboard

Esse é o produto.

&nbsp;