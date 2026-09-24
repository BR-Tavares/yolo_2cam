import streamlit as st
import pandas as pd
import sqlite3
import os
import time
import cv2
import numpy as np
import json
import sys

# Adiciona o diretório raiz ao sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from monitoramento_feira.config import AppConfig, CONFIG_PATH
from monitoramento_feira.captura import test_camera_device
from monitoramento_feira.banco import Database

st.set_page_config(
    page_title="Painel de Controle e Análise — Feira",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Carrega configuração atual
cfg = AppConfig.load()
db = Database(cfg.db_path)

st.title("📡 Sistema de Monitoramento & Engajamento — Stand")

tabs = st.tabs(["🎥 Configuração de Câmeras", "📐 Calibração Homografia", "📊 Painel Analítico", "🌐 Telas Públicas"])

# ==========================================
# ABA 1: CONFIGURAÇÃO DE CÂMERAS
# ==========================================
with tabs[0]:
    st.subheader("Gerenciamento de Fontes de Vídeo")
    st.markdown("""
    Configure as câmeras de acordo com o ambiente. Para testes neste computador, utilize o **Modo Webcam Única**. 
    No notebook da feira com duas câmeras físicas, selecione **2 Câmeras Independentes**.
    """)

    col_mode, col_test = st.columns([2, 1])
    with col_mode:
        modo_operacao = st.radio(
            "Modo de Operação de Câmeras:",
            options=["Webcam Única (Ambiente de Testes)", "2 Câmeras Independentes (Notebook na Feira)"],
            index=0 if cfg.single_camera_mode else 1
        )
        is_single = (modo_operacao == "Webcam Única (Ambiente de Testes)")

    with col_test:
        st.markdown("**Status do Backend & Câmeras**")
        backend_online = False
        try:
            import urllib.request
            with urllib.request.urlopen(f"http://localhost:{cfg.api_port}/api/status", timeout=1.0) as resp:
                data = json.loads(resp.read().decode())
                cams = data.get("cameras", {})
                st.success("🟢 Backend de Monitoramento: Ativo")
                st.caption(f"Fonte A: {'Online' if cams.get('source_a_online') else 'Offline'} | Fonte B: {'Online' if cams.get('source_b_online') else 'Offline'}")
                backend_online = True
        except Exception:
            st.warning("🟡 Backend de Monitoramento: Não detectado na porta " + str(cfg.api_port))

        if st.button("🔍 Diagnosticar Portas de Câmera"):
            if backend_online:
                st.info("A webcam está atualmente em uso contínuo pelo pipeline de monitoramento (Status: Conectada e Operando).")
            else:
                ok0, msg0 = test_camera_device(0)
                ok1, msg1 = test_camera_device(1)
                st.info(f"Dispositivo 0: {msg0}")
                if ok1:
                    st.success(f"Dispositivo 1: {msg1}")
                else:
                    st.warning(f"Dispositivo 1: {msg1}")

    st.divider()
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### 📷 Fonte A: Público / Trajetória (Câmera Elevada)")
        st.caption("Responsável pelo monitoramento do fluxo e alimentação da Tela Radar.")
        cam_a_input = st.text_input("Índice do dispositivo ou URL:", value=str(cfg.camera_a_source), key="cam_a_src")
        cam_a_enabled = st.checkbox("Habilitar Fonte A", value=cfg.camera_a_enabled, key="cam_a_en")

    with c2:
        st.markdown("### 📷 Fonte B: Engajamento (Câmera Notebook / Frontal)")
        st.caption("Responsável pela detecção de aproximação, atenção e pose de cabeça.")
        cam_b_input = st.text_input(
            "Índice do dispositivo ou URL:",
            value=str(cfg.camera_b_source),
            disabled=is_single,
            help="Desabilitado no modo de webcam única (o sistema multiplexa a Fonte A automaticamente)",
            key="cam_b_src"
        )
        cam_b_enabled = st.checkbox("Habilitar Fonte B", value=cfg.camera_b_enabled, key="cam_b_en")


    if st.button("💾 Salvar e Aplicar Configuração de Câmeras", type="primary"):
        # Trata inteiros vs strings/URLs
        cfg.camera_a_source = int(cam_a_input) if cam_a_input.isdigit() else cam_a_input
        cfg.camera_b_source = int(cam_b_input) if cam_b_input.isdigit() else cam_b_input
        cfg.camera_a_enabled = cam_a_enabled
        cfg.camera_b_enabled = cam_b_enabled
        cfg.single_camera_mode = is_single
        cfg.save()
        st.success("Configuração de câmeras salva com sucesso! Reinicie o backend se necessário para aplicar novas portas de hardware.")

    st.divider()
    st.markdown("#### Imagem ao Vivo da Câmera (Com Detecções do Modelo)")
    if st.button("📸 Capturar Frame ao Vivo"):
        preview_captured = False
        # Tenta pegar do backend em execução primeiro (evita conflito de hardware lock)
        try:
            import urllib.request
            req = urllib.request.Request(f"http://localhost:{cfg.api_port}/api/preview_a")
            with urllib.request.urlopen(req, timeout=2.0) as response:
                img_bytes = response.read()
                st.image(img_bytes, caption=f"Frame ao vivo processado da Câmera (Fonte A: {cfg.camera_a_source})", use_container_width=True)
                preview_captured = True
        except Exception:
            pass

        if not preview_captured:
            # Fallback direto caso o backend esteja desligado
            try:
                from monitoramento_feira.captura import VideoSource
                test_src = cfg.camera_a_source
                vs = VideoSource(test_src, "PreviewTest")
                vs.start()
                time.sleep(1.0)
                frame = vs.get_frame()
                vs.stop()

                if frame is not None:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    st.image(rgb, caption=f"Frame capturado da Fonte A ({test_src})", use_container_width=True)
                else:
                    st.error("Não foi possível obter imagem da câmera selecionada. Verifique se o backend está executando ou se outro aplicativo está utilizando a webcam.")
            except Exception as e:
                st.error(f"Erro ao testar preview: {e}")


# ==========================================
# ABA 2: CALIBRAÇÃO HOMOGRAFIA
# ==========================================
with tabs[1]:
    st.subheader("Calibração Espacial da Câmera Elevada (Homografia)")
    st.markdown("""
    Marque os 4 pontos de referência no chão que delimitam a área de projeção para o radar concêntrico.
    Caso o tripé da câmera sofra qualquer solavanco, reajuste as coordenadas abaixo e salve.
    """)

    pts = cfg.homografia_src_pts
    cp1, cp2, cp3, cp4 = st.columns(4)

    with cp1:
        st.markdown("**Ponto 1 (Topo-Esquerda)**")
        p1_x = st.number_input("P1 X:", value=float(pts[0][0]), step=10.0, key="p1x")
        p1_y = st.number_input("P1 Y:", value=float(pts[0][1]), step=10.0, key="p1y")
    with cp2:
        st.markdown("**Ponto 2 (Topo-Direita)**")
        p2_x = st.number_input("P2 X:", value=float(pts[1][0]), step=10.0, key="p2x")
        p2_y = st.number_input("P2 Y:", value=float(pts[1][1]), step=10.0, key="p2y")
    with cp3:
        st.markdown("**Ponto 3 (Base-Direita)**")
        p3_x = st.number_input("P3 X:", value=float(pts[2][0]), step=10.0, key="p3x")
        p3_y = st.number_input("P3 Y:", value=float(pts[2][1]), step=10.0, key="p3y")
    with cp4:
        st.markdown("**Ponto 4 (Base-Esquerda)**")
        p4_x = st.number_input("P4 X:", value=float(pts[3][0]), step=10.0, key="p4x")
        p4_y = st.number_input("P4 Y:", value=float(pts[3][1]), step=10.0, key="p4y")

    inv_x = st.checkbox(
        "Espelhar Eixo Horizontal (Inverter Direita/Esquerda)",
        value=cfg.inverter_eixo_x,
        help="Garante que mover-se para a sua direita mova o cometa para a direita da tela."
    )

    if st.button("📐 Salvar Nova Calibração", type="primary"):
        cfg.inverter_eixo_x = inv_x
        cfg.homografia_src_pts = [
            [p1_x, p1_y],
            [p2_x, p2_y],
            [p3_x, p3_y],
            [p4_x, p4_y]
        ]
        cfg.save()
        st.success("Calibração e orientação de eixos salvas com sucesso!")


# ==========================================
# ABA 3: PAINEL ANALÍTICO
# ==========================================
with tabs[2]:
    st.subheader("Métricas de Tráfego e Engajamento (Leitura SQLite)")
    
    col_act, _ = st.columns([1, 3])
    with col_act:
        if st.button("🔄 Atualizar Métricas"):
            st.rerun()

    # Cards KPI
    resumo = db.obter_resumo_geral()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Visitantes Únicos", resumo["total_visitantes"])
    k2.metric("Permanência Média no Stand", f"{resumo['tempo_medio_zona']} s")
    k3.metric("Engajamentos Válidos (≥3s)", resumo["total_engajamentos_validos"])
    k4.metric("Score Médio de Atenção", f"{int(resumo['score_medio'] * 100)} %")

    st.divider()

    # Gráficos a partir das tabelas SQLite
    conn = sqlite3.connect(cfg.db_path)
    try:
        df_traj = pd.read_sql_query("SELECT id, track_id, datetime(inicio_ts, 'unixepoch', 'localtime') as inicio, tempo_na_zona FROM sessoes_trajetoria ORDER BY id DESC LIMIT 100", conn)
        df_eng = pd.read_sql_query("SELECT id, sessao_id, datetime(inicio_ts, 'unixepoch', 'localtime') as inicio, dwell_time, facing_time, engagement_score FROM sessoes_engajamento WHERE dwell_time >= 3.0 ORDER BY id DESC LIMIT 100", conn)
        
        c_left, c_right = st.columns(2)
        with c_left:
            st.markdown("#### Últimas Sessões no Stand (Trajetória)")
            if not df_traj.empty:
                st.dataframe(df_traj, use_container_width=True)
            else:
                st.info("Nenhuma sessão de trajetória registrada ainda.")

        with c_right:
            st.markdown("#### Últimas Sessões de Engajamento Válidas")
            if not df_eng.empty:
                st.dataframe(df_eng, use_container_width=True)
            else:
                st.info("Nenhuma sessão de engajamento registrada ainda.")

        # Consolidação de janelas
        st.markdown("#### Histórico Agregado de Janelas (5 min)")
        df_agg = pd.read_sql_query("SELECT id, datetime(janela_inicio, 'unixepoch', 'localtime') as inicio, visitantes_unicos, tempo_medio_zona, engajamentos_validos, score_medio FROM agregados_janela ORDER BY id DESC LIMIT 20", conn)
        if not df_agg.empty:
            st.line_chart(df_agg.set_index("inicio")[["visitantes_unicos", "engajamentos_validos"]])
        else:
            st.caption("Ainda não há janelas agregadas. O agregador consolida os dados automaticamente a cada 5 minutos.")

    except Exception as e:
        st.warning(f"Banco de dados ainda sem dados para exibição: {e}")
    finally:
        conn.close()

# ==========================================
# ABA 4: TELAS PÚBLICAS
# ==========================================
with tabs[3]:
    st.subheader("Atalhos para as Telas de Exibição Pública")
    st.markdown("""
    Estas telas são projetadas para exibição em monitores voltados aos visitantes do stand.
    """)
    radar_url = f"http://localhost:{cfg.api_port}/radar"
    eng_url = f"http://localhost:{cfg.api_port}/engajamento"

    c_r, c_e = st.columns(2)
    with c_r:
        st.markdown(f"### 🌐 [Abrir Tela Radar]({radar_url})")
        st.write("Visão aérea abstrata com fluxo de visitantes e rastro estilo cometa.")
    with c_e:
        st.markdown(f"### ⚡ [Abrir Tela de Engajamento]({eng_url})")
        st.write("Experiência interativa responsiva que reage à atenção do visitante diante do notebook.")
