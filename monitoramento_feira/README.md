# Sistema de Monitoramento e Engajamento de Stand (Feira)

Implementação de referência baseada na especificação `Planos/02-especificacao-monitoramento-feira.md`.

## 📁 Estrutura de Arquivos

```
monitoramento_feira/
├── config.py                 # Configurações com persistência em config.json
├── banco.py                  # Schema SQLite, inserções e agregações periódicas
├── captura.py                # Thread de captura com suporte a 1 ou 2 câmeras
├── estado.py                 # Estados em memória (TrajectoryState e EngagementState)
├── modelo_trajetoria.py      # Modelo A: YOLO + ByteTrack + Homografia + Zona
├── modelo_engajamento.py     # Modelo B: YOLO Pose/Face + solvePnP (Yaw/Pitch)
├── radar_server.py           # Servidor FastAPI com endpoints e páginas HTML5
├── dashboard.py              # Painel privado Streamlit (Câmeras, Calibração, Métricas)
├── run.py                    # Loop principal orquestrador e inicializador do servidor
├── static/
│   ├── radar.html            # Tela pública com radar concêntrico e rastro cometa
│   └── engajamento.html      # Tela pública interativa com energímetro visual
└── README.md                 # Documentação de operação
```

---

## 🚀 Como Executar

### 1. Iniciar o Sistema de Monitoramento e Servidor do Radar
No terminal, execute:
```bash
python -m monitoramento_feira.run
```
O serviço iniciará:
- O loop de captura e inferência das câmeras
- A persistência de sessões no banco SQLite `feira_monitoramento.db`
- As telas públicas:
  - **Tela Radar:** [http://localhost:8000/radar](http://localhost:8000/radar)
  - **Tela de Engajamento:** [http://localhost:8000/engajamento](http://localhost:8000/engajamento)

### 2. Iniciar o Painel de Controle & Análise (Streamlit)
Em outro terminal:
```bash
streamlit run monitoramento_feira/dashboard.py
```
Acesse o painel em [http://localhost:8501](http://localhost:8501).

---

## 🎥 Configuração de Câmeras no Dashboard

### Testando neste computador (1 Webcam Instalada):
1. Abra o painel em [http://localhost:8501](http://localhost:8501) na aba **🎥 Configuração de Câmeras**.
2. Deixe selecionado **Webcam Única (Ambiente de Testes)**.
3. Nesse modo, o sistema abre apenas a sua webcam física (`0`) e multiplexa os quadros para ambos os pipelines (trajetória de pessoas e engajamento facial), evitando o bloqueio de hardware do Windows.
4. Clique no botão **"📸 Capturar Frame de Validação"** para testar a imagem ao vivo.

### No Notebook na Feira (2 Câmeras Independentes):
1. Conecte a webcam USB no tripé elevado (Fonte A) e use a câmera embutida do notebook (Fonte B).
2. Na aba **🎥 Configuração de Câmeras**, selecione **2 Câmeras Independentes (Notebook na Feira)**.
3. Configure os índices de cada câmera (ex: Fonte A = `1` ou `0`, Fonte B = `0` ou `1`).
4. Utilize o botão **"🔍 Testar Câmeras Disponíveis"** para verificar qual índice corresponde a qual câmera.
5. Clique em **"💾 Salvar e Aplicar Configuração de Câmeras"**.

---

## 📐 Calibração da Homografia (Câmera Elevada)
1. No dashboard, acesse a aba **📐 Calibração Homografia**.
2. Ajuste as coordenadas dos 4 pontos de referência no chão (`P1, P2, P3, P4`).
3. Clique em **"📐 Salvar Nova Calibração"**. A nova matriz de homografia é aplicada imediatamente no pipeline de radar sem precisar reiniciar o sistema.

---

## 🔒 Princípios de Privacidade
- Nenhum frame de vídeo é gravado em disco.
- Nenhum modelo de reconhecimento facial ou biometria é utilizado.
- São armazenados apenas métricas tabulares e agregados numéricos em SQLite.
