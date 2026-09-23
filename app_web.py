import os
import re
import sqlite3
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st

# =========================================================
# CONFIGURAÇÃO DA PÁGINA E DIRETÓRIOS
# =========================================================
st.set_page_config(
    page_title="Estoque Requipel",
    page_icon="📦",
    layout="wide"
)

ARQUIVO_BANCO = "banco_almoxarifado.db"
PASTA_UPLOADS = "uploads_conserto"

if not os.path.exists(PASTA_UPLOADS):
    os.makedirs(PASTA_UPLOADS)

def conectar_banco():
    return sqlite3.connect(ARQUIVO_BANCO)

# =========================================================
# INICIALIZAÇÃO DO BANCO DE DADOS
# =========================================================
def inicializar_banco():
    conn = conectar_banco()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    cursor.execute("SELECT valor FROM configuracoes WHERE chave='data_instalacao'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('data_instalacao', ?)", (datetime.now().strftime("%Y-%m-%d"),))

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pecas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            quantidade INTEGER DEFAULT 0,
            ncm TEXT NOT NULL,
            categoria TEXT,
            localizacao TEXT,
            qtd_minima INTEGER DEFAULT 1,
            valor_unitario REAL DEFAULT 0.0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS consertos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_nome TEXT NOT NULL,
            cod_ref TEXT,
            data_envio TEXT,
            oficina TEXT,
            num_nf TEXT,
            defeito TEXT,
            caminho_foto_peca TEXT,
            caminho_foto_nf TEXT,
            status TEXT DEFAULT 'Em Conserto'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            tipo TEXT,
            item_nome TEXT,
            quantidade INTEGER,
            observacao TEXT,
            usuario TEXT DEFAULT 'Sistema'
        )
    """)
    
    conn.commit()
    conn.close()

inicializar_banco()

# =========================================================
# TRAVA DE SEGURANÇA (90 DIAS)
# =========================================================
def verificar_licenca():
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT valor FROM configuracoes WHERE chave='master_unlocked'")
    unlocked = cursor.fetchone()
    if unlocked and unlocked[0] == '1':
        conn.close()
        return True

    cursor.execute("SELECT valor FROM configuracoes WHERE chave='data_instalacao'")
    res = cursor.fetchone()
    conn.close()
    
    if res:
        data_inst = datetime.strptime(res[0], "%Y-%m-%d")
        if (datetime.now() - data_inst).days > 90:
            st.error("🔒 LICENÇA EXPIRADA - Bloqueio de Segurança Ativado")
            codigo = st.text_input("Insira o Código Master de Liberação:", type="password")
            if st.button("Desbloquear Sistema"):
                if codigo == "202739":
                    conn = conectar_banco()
                    cursor = conn.cursor()
                    cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('master_unlocked', '1')")
                    conn.commit()
                    conn.close()
                    st.success("Licença desbloqueada!")
                    st.rerun()
                else:
                    st.error("Código incorreto.")
            return False
    return True

if not verificar_licenca():
    st.stop()

# =========================================================
# LOGIN
# =========================================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.markdown("<h1 style='text-align: center;'>🔑 Acesso ao Sistema - Estoque Requipel</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login_form"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("ENTRAR"):
                if (usuario.lower() == "admin" and senha == "1234") or (usuario.lower() == "almox" and senha == "rqp123"):
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_logado"] = usuario
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")
    st.stop()

# =========================================================
# MENU LATERAL E NAVEGAÇÃO
# =========================================================
st.sidebar.title("🏢 Almoxarifado Requipel")
st.sidebar.caption(f"Usuário: {st.session_state.get('usuario_logado', 'Admin')}")

if st.sidebar.button("🚪 Sair"):
    st.session_state["autenticado"] = False
    st.rerun()

st.sidebar.divider()

menu = st.sidebar.radio(
    "Menu:",
    ["📊 Visão Geral / Dashboard", "🛠️ Gestão de Consertos", "📦 Movimentação de Estoque", "➕ Cadastrar / Editar Peças", "📜 Histórico Geral", "🔍 Consulta Rápida NCM"]
)

# =========================================================
# MÓDULO: GESTÃO DE CONSERTOS
# =========================================================
if menu == "🛠️ Gestão de Consertos":
    st.title("🛠️ Gestão de Peças em Conserto / Manutenção")
    
    with st.expander("➕ Enviar Nova Peça para Conserto", expanded=False):
        with st.form("form_conserto_novo", clear_on_submit=True):
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                item_nome = st.text_input("Nome do Item / Peça *")
                cod_ref = st.text_input("Código Interno ou REF")
                oficina = st.text_input("Oficina / Empresa de Manutenção *")
            with f_col2:
                num_nf = st.text_input("Nº da Nota Fiscal de Remessa")
                defeito = st.text_area("Descrição do Defeito")
            
            f_img1, f_img2 = st.columns(2)
            with f_img1:
                f_peca = st.file_uploader("Foto da Peça", type=["png", "jpg", "jpeg"])
            with f_img2:
                f_nf = st.file_uploader("Foto da Nota Fiscal", type=["png", "jpg", "jpeg"])
            
            if st.form_submit_button("🚀 Confirmar Envio"):
                if not item_nome or not oficina:
                    st.error("Preencha o Nome do Item e a Oficina.")
                else:
                    p_peca = ""
                    p_nf = ""
                    if f_peca:
                        p_peca = os.path.join(PASTA_UPLOADS, f"peca_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{f_peca.name}")
                        with open(p_peca, "wb") as f:
                            f.write(f_peca.getbuffer())
                    if f_nf:
                        p_nf = os.path.join(PASTA_UPLOADS, f"nf_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{f_nf.name}")
                        with open(p_nf, "wb") as f:
                            f.write(f_nf.getbuffer())

                    conn = conectar_banco()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO consertos (item_nome, cod_ref, data_envio, oficina, num_nf, defeito, caminho_foto_peca, caminho_foto_nf, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Em Conserto')
                    """, (item_nome, cod_ref, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), oficina, num_nf, defeito, p_peca, p_nf))
                    conn.commit()
                    conn.close()
                    st.success("Enviado com sucesso!")
                    st.rerun()

    st.divider()

    conn = conectar_banco()
    df_consertos = pd.read_sql_query("SELECT * FROM consertos WHERE status != 'Retornado' ORDER BY id DESC", conn)
    conn.close()

    if df_consertos.empty:
        st.info("Nenhuma peça em conserto no momento.")
    else:
        for idx, row in df_consertos.iterrows():
            col_img, col_detalhes, col_status = st.columns([1.5, 3, 1.5])
            
            with col_img:
                col_p, col_nf = st.columns(2)
                with col_p:
                    st.caption("📷 Foto Peça")
                    if row['caminho_foto_peca'] and os.path.exists(row['caminho_foto_peca']):
                        st.image(row['caminho_foto_peca'], use_container_width=True)
                    else:
                        st.info("Sem foto")
                with col_nf:
                    st.caption("📄 Foto NF")
                    if row['caminho_foto_nf'] and os.path.exists(row['caminho_foto_nf']):
                        st.image(row['caminho_foto_nf'], use_container_width=True)
                    else:
                        st.info("Sem foto NF")

            with col_detalhes:
                st.subheader(f"**{row['item_nome']}**")
                st.write(f"**Cód. Interno/REF:** {row['cod_ref'] if row['cod_ref'] else 'N/A'}")
                st.write(f"**Data de Envio:** {row['data_envio']}")
                st.write(f"**Oficina / Empresa:** {row['oficina']}")
                st.write(f"**Nº NF:** {row['num_nf']}")
                st.write(f"**Defeito:** {row['defeito']}")

            with col_status:
                opcoes_status = ["Em Conserto", "Em espera de coleta"]
                status_atual = row['status'] if row['status'] in opcoes_status else "Em Conserto"
                
                novo_status = st.selectbox(
                    "Status Atual:",
                    opcoes_status,
                    index=opcoes_status.index(status_atual),
                    key=f"status_{row['id']}"
                )
                
                if novo_status != row['status']:
                    conn = conectar_banco()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE consertos SET status = ? WHERE id = ?", (novo_status, row['id']))
                    conn.commit()
                    conn.close()
                    st.success("Status alterado!")
                    st.rerun()

                st.write("---")
                with st.popover("✅ Registrar Retorno"):
                    if st.button("Confirmar Retorno", key=f"ret_{row['id']}"):
                        conn = conectar_banco()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE consertos SET status = 'Retornado' WHERE id = ?", (row['id'],))
                        conn.commit()
                        conn.close()
                        st.success("Retorno registrado!")
                        st.rerun()

            st.divider()

# =========================================================
# DEMAIS MÓDULOS (DASHBOARD, ESTOQUE, CADASTRO, HISTÓRICO)
# =========================================================
elif menu == "📊 Visão Geral / Dashboard":
    st.title("📊 Painel Geral do Estoque")
    conn = conectar_banco()
    df_pecas = pd.read_sql_query("SELECT * FROM pecas", conn)
    conn.close()
    st.dataframe(df_pecas, use_container_width=True)

elif menu == "📦 Movimentação de Estoque":
    st.title("📦 Movimentação de Peças")

elif menu == "➕ Cadastrar / Editar Peças":
    st.title("➕ Cadastrar / Editar Peças")
    with st.form("form_cad"):
        codigo = st.text_input("Código *")
        nome = st.text_input("Nome *")
        ncm = st.text_input("NCM (XXXX.XX.XX) *")
        if st.form_submit_button("Salvar"):
            if not re.match(r"^\d{4}\.\d{2}\.\d{2}$", ncm):
                st.error("Formato NCM Inválido! Use XXXX.XX.XX")
            else:
                conn = conectar_banco()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO pecas (codigo, nome, ncm) VALUES (?, ?, ?)", (codigo, nome, ncm))
                conn.commit()
                conn.close()
                st.success("Cadastrado!")

elif menu == "📜 Histórico Geral":
    st.title("📜 Histórico")

elif menu == "🔍 Consulta Rápida NCM":
    st.title("🔍 Consulta NCM")
