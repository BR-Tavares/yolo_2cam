# YOLO 2-Cam: Monitoramento Espacial & Engajamento para Feiras e Estandes

Sistema integrado de visão computacional em tempo real desenvolvido para estandes em feiras de negócios e tecnologia. O sistema utiliza duas fontes de vídeo (ou uma webcam multiplexada) para monitorar o **fluxo de tráfego do público** e medir o **engajamento visual de visitantes** de forma 100% anônima e em conformidade com as diretrizes de privacidade/LGPD (sem gravação de imagens, sem identificação facial e sem retenção biométrica).

---

## 🏛️ Arquitetura do Sistema

```
                         ┌────────────────────────────────────────────────┐
                         │              FONTES DE VÍDEO                   │
                         │  • Câmera A (Elevada / Público no Corredor)    │
                         │  • Câmera B (Frontal / Visitantes na Bancada)  │
                         │  (Ou Webcam Única Multiplexada para Testes)    │
                         └──────────────────────┬─────────────────────────┘
                                                │ Frames BGR
                                                ▼
                         ┌────────────────────────────────────────────────┐
                         │           PIPELINES DE INFERÊNCIA              │
                         │  • Pipeline A: YOLO11n + ByteTrack             │
                         │    -> Projeção Homográfica 2D (Chão do Stand)  │
                         │  • Pipeline B: YOLOv8n-Pose                    │
                         │    -> Head Pose (solvePnP SQPNP + Simetria)    │
                         └──────────────────────┬─────────────────────────┘
                                                │ Estados em Memória
                                                ▼
                         ┌────────────────────────────────────────────────┐
                         │       BACKEND FASTAPI (Porta 8000)             │
                         │  • /radar ➔ Tela Pública: Fluxo de Cometas     │
                         │  • /engajamento ➔ Tela Interativa da Bancada   │
                         │  • /api/radar & /api/engajamento (JSON em 150ms│
                         │  • SQLite: Persistência Contínua de Sessões    │
                         └──────────────────────┬─────────────────────────┘
                                                │ Leitura SQLite & HTTP
                                                ▼
                         ┌────────────────────────────────────────────────┐
                         │     DASHBOARD STREAMLIT (Porta 8501)           │
                         │  • Calibração de Homografia 2D Interativa      │
                         │  • Gestão de Câmeras (Webcam Única vs. 2 Cams) │
                         │  • Audience Measurement Time Series Automático │
                         └────────────────────────────────────────────────┘
```

---

## 🖥️ Telas e Módulos Disponíveis

| Módulo / Tela | URL Local | Descrição |
| :--- | :--- | :--- |
| **Radar Espacial de Visitantes** | `http://localhost:8000/radar` | Interface visual futurista estilo HUD que plota a movimentação de passantes em perspectiva espacial. Cometas com cauda de partículas em 3 cores: <br>• 🟢 **Verde**: Na Área de Engajamento da Bancada;<br>• 🔵 **Azul**: Prestando atenção / olhando para o stand de longe;<br>• 🟠 **Laranja**: Em trânsito pelo corredor. |
| **Centro de Engajamento Interativo** | `http://localhost:8000/engajamento` | Tela pública voltada ao visitante na bancada. Exibe contador dinâmico de pessoas conectadas visualmente, barra de energia coletiva, cartões dinâmicos de visitantes e reações em tempo real. |
| **Dashboard Administrativo** | `http://localhost:8501` | Painel Streamlit completo com:<br>1. **Seleção de Câmeras**: Alternância entre 1 webcam e 2 câmeras físicas independentes;<br>2. **Calibração Espacial**: Ajuste dos 4 pontos de ancoragem da homografia com preview ao vivo;<br>3. **Audience Measurement**: Séries temporais automáticas por minuto (Footfall, Engajamentos, Capture Rate %, Dwell Time, Atenção Qualificada) com filtro temporal (15 min, 1h, Hoje, Histórico). |

---

## 📦 Estrutura de Pastas

```
yolo_2cam/
├── monitoramento_feira/
│   ├── static/
│   │   ├── radar.html           # Canvas HUD do radar espacial de cometas
│   │   └── engajamento.html     # Tela interativa voltada para a bancada
│   ├── banco.py                 # Camada SQLite com upsert em tempo real e agregação temporal
│   ├── captura.py               # Multiplexador de câmeras (suporte a 1 webcam ou 2 independentes)
│   ├── config.py & config.json  # Configurações de homografia, limiares de pose e portas
│   ├── dashboard.py             # Dashboard administrativo Streamlit
│   ├── estado.py                # Gerenciadores de estado em memória (TrajectoryState & EngagementState)
│   ├── modelo_engajamento.py    # YOLOv8-pose + solvePnP (SQPNP) + simetria de cabeça e ombros
│   ├── modelo_trajetoria.py     # YOLO11 + ByteTrack + Transformação de perspectiva 2D
│   ├── radar_server.py          # API REST FastAPI e servidor web
│   └── run.py                   # Orquestrador principal multi-thread
├── Planos/                      # Documentos de especificação e métricas analíticas
├── requirements.txt             # Dependências Python
└── README.md                    # Esta documentação
```

---

## 🛠️ Guia de Instalação para Outra Máquina (Instruções para IA ou Desenvolvedor)

Siga os passos abaixo para instalar e rodar o projeto a partir do zero em qualquer computador com Windows ou Linux.

### 1. Clonar o Repositório
```bash
git clone https://github.com/BR-Tavares/yolo_2cam.git
cd yolo_2cam
```

### 2. Criar e Ativar o Ambiente Virtual Python (Recomendado: Python 3.10+)
- **Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```
- **Linux / macOS:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Instalar Dependências
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Nota sobre Pesos dos Modelos:** Não é necessário baixar arquivos `.pt` manualmente. O pacote `ultralytics` fará o download automático de `yolo11n.pt` e `yolov8n-pose.pt` na primeira execução.

---

## ▶️ Como Executar a Aplicação

O sistema opera com dois processos simultâneos: o **Backend de Visão Computacional (FastAPI)** e o **Dashboard de Controle (Streamlit)**.

### Terminal 1: Iniciar o Backend
```bash
python -m monitoramento_feira.run
```
*O backend inicializa os modelos neurais, abre a(s) câmera(s) e disponibiliza as portas `8000` (FastAPI) e os endpoints do radar e engajamento.*

### Terminal 2: Iniciar o Dashboard Streamlit
```bash
python -m streamlit run monitoramento_feira/dashboard.py --server.port 8501
```
*O dashboard administrativo estará acessível no navegador em: `http://localhost:8501`.*

---

## ⚙️ Configuração de Câmeras: Notebook da Feira vs. Máquina de Teste

O sistema possui inteligência para operar tanto com **1 única webcam** quanto com **2 câmeras físicas independentes**:

### Cenário 1: Testes em Computador com Apenas 1 Webcam (Padrão)
- No `config.json` ou no Streamlit (Aba 1), deixe marcado: **"Modo de Webcam Única (Multiplexada)"**.
- O sistema abre a câmera `0` apenas uma vez no hardware do sistema operacional e compartilha os frames de forma assíncrona entre o Modelo de Trajetória e o Modelo de Engajamento, evitando travamentos de hardware no Windows.

### Cenário 2: Demonstração na Feira com 2 Câmeras Físicas
1. Conecte as duas câmeras USB no notebook da feira:
   - **Câmera A**: Câmera elevada apontada para o corredor/fluxo do público.
   - **Câmera B**: Câmera frontal no notebook apontada para quem está diante da bancada.
2. Abra o dashboard em `http://localhost:8501` e vá na **Aba 1 (Configuração de Câmeras)**:
   - **Desmarque** o *Modo de Webcam Única*;
   - Configure o índice da Fonte A (ex: `0`) e da Fonte B (ex: `1` ou URL RTSP/IP);
   - Clique em **Salvar e Aplicar Configuração de Câmeras**.

---

## 📐 Calibração Espacial da Homografia 2D (Aba 2)

Para projetar as pessoas no chão do estande no Radar:
1. Acesse `http://localhost:8501` na **Aba 2 (Calibração Homografia)**;
2. Visualize o frame ao vivo da Câmera A com os 4 pontos demarcados no chão ($P_1, P_2, P_3, P_4$);
3. Ajuste as coordenadas caso o tripé ou a câmera sofra algum desvio durante a montagem do estande;
4. Se ao se mover para a direita o cometa for para a esquerda, marque a opção **"Espelhar Eixo Horizontal"**.

---

## 📊 Métricas de Audience Measurement (Aba 3)

O sistema registra cada sessão continuamente no SQLite (`feira_monitoramento.db`) com data e hora exatas, gerando gráficos de séries temporais de forma 100% automática:

- **Footfall (Fluxo Total)**: Quantidade de pessoas únicas detectadas no período;
- **Engajamentos Válidos**: Visitantes que permaneceram na bancada por 3 segundos ou mais;
- **Taxa de Captura (Capture Rate %)**: $\frac{\text{Engajamentos Válidos}}{\text{Footfall}}$ — poder de atração da bancada;
- **Dwell Time Médio**: Tempo médio de permanência ativa diante da bancada;
- **Atenção Qualificada (Engagement Rate %)**: Proporção de visitantes que mantiveram contato visual direto.

> **Filtro Temporal Dinâmico:** No topo da Aba 3, selecione entre `Últimos 15 min`, `Última 1 hora`, `Dia de Hoje` ou `Histórico Completo`. Os gráficos e totais são recalculados em tempo real sem necessidade de ações manuais.

---

## 🔌 Principais Endpoints da API REST (`http://localhost:8000`)

| Método | Endpoint | Retorno / Função |
| :--- | :--- | :--- |
| `GET` | `/radar` | Página HTML do Radar Espacial com renderização por Canvas 2D |
| `GET` | `/engajamento` | Página HTML da tela de engajamento do visitante |
| `GET` | `/api/radar` | JSON com lista de cometas, posições `(X, Y)`, trilha e status (`na_zona`, `olhando`) |
| `GET` | `/api/engajamento` | JSON com métricas ao vivo (`count`, `total_olhando`, `energia_coletiva`, lista de visitantes) |
| `GET` | `/api/status` | Diagnóstico de status de hardware das câmeras e contadores em memória |
| `GET` | `/api/preview_a` | Snapshot JPEG anotado com detecções da Câmera A |
| `GET` | `/api/preview_b` | Snapshot JPEG anotado com detecções da Câmera B |
| `POST` | `/api/recalibrate` | Atualiza os 4 pontos de homografia a quente sem reiniciar o processo |
| `POST` | `/api/reset` | Reseta a memória ativa de rastreamento do sistema |

---

## 🔒 Privacidade e Conformidade (LGPD)

O sistema foi arquitetado segundo princípios de *Privacy by Design*:
1. **Nenhuma imagem facial ou vídeo de visitantes é salvo em disco ou enviado para a nuvem.**
2. O modelo de pose apenas extrai coordenadas numéricas relativas de pontos anatômicos (nariz, olhos e ombros) para calcular o vetor direcional de atenção via algoritmos geométricos locais (`solvePnP SQPNP`).
3. O rastreamento de público atribui identificadores efêmeros baseados em cinemática (`track_id`), sem cruzamento com bases externas de dados pessoais.

---

## 📜 Licença

Desenvolvido para demonstração e monitoramento de eventos de tecnologia. Distribuído sob os termos de uso do projeto.
