import os
import re
import sqlite3
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st

# =========================================================
# CONFIGURAÇÃO DA PÁGINA
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
    res = cursor.fetchone()
    if not res:
        cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('data_instalacao', ?)", (datetime.now().strftime("%Y-%m-%d"),))
        conn.commit()

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
    data_str = cursor.fetchone()[0]
    conn.close()
    
    data_inst = datetime.strptime(data_str, "%Y-%m-%d")
    dias_passados = (datetime.now() - data_inst).days
    
    if dias_passados > 90:
        st.error("🔒 LICENÇA EXPIRADA - Bloqueio de Segurança Ativado")
        codigo = st.text_input("Insira o Código Master de Liberação:", type="password")
        if st.button("Desbloquear Sistema"):
            if codigo == "202739":
                conn = conectar_banco()
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('master_unlocked', '1')")
                conn.commit()
                conn.close()
                st.success("Licença validada!")
                st.rerun()
            else:
                st.error("Código incorreto.")
        return False
    return True

if not verificar_licenca():
    st.stop()

# =========================================================
# TELA PRINCIPAL - GESTÃO DE CONSERTOS (COM O NOVO STATUS)
# =========================================================
st.title("🛠️ Gestão de Peças em Conserto / Manutenção")

conn = conectar_banco()
df_consertos = pd.read_sql_query("SELECT * FROM consertos WHERE status != 'Retornado' ORDER BY id DESC", conn)
conn.close()

if df_consertos.empty:
    st.info("Nenhuma peça em conserto ou aguardando coleta no momento.")
else:
    for idx, row in df_consertos.iterrows():
        col_img, col_detalhes, col_status = st.columns([1.5, 3, 1.5])
        
        with col_img:
            col_p, col_nf = st.columns(2)
            with col_p:
                st.caption("📷 Foto da Peça")
                if row['caminho_foto_peca'] and os.path.exists(row['caminho_foto_peca']):
                    st.image(row['caminho_foto_peca'], use_container_width=True)
                else:
                    st.info("Sem foto cadastrada")
            with col_nf:
                st.caption("📄 Foto da NF")
                if row['caminho_foto_nf'] and os.path.exists(row['caminho_foto_nf']):
                    st.image(row['caminho_foto_nf'], use_container_width=True)
                else:
                    st.info("Sem foto da NF")

        with col_detalhes:
            st.subheader(f"**{row['item_nome']}**")
            st.write(f"**Cód. Interno/REF:** {row['cod_ref'] if row['cod_ref'] else 'N/A'}")
            st.write(f"**Data de Envio:** {row['data_envio']}")
            st.write(f"**Oficina / Empresa:** {row['oficina']}")
            st.write(f"**Nº da NF de Remessa:** {row['num_nf']}")
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
                st.success("Status atualizado!")
                st.rerun()

            st.write("---")
            with st.popover("✅ Registrar Retorno"):
                st.write("Confirmar o retorno desta peça ao estoque?")
                if st.button("Confirmar Retorno ao Estoque", key=f"ret_{row['id']}"):
                    conn = conectar_banco()
                    cursor = conn.cursor()
                    cursor.execute("UPDATE consertos SET status = 'Retornado' WHERE id = ?", (row['id'],))
                    conn.commit()
                    conn.close()
                    st.success("Retorno registrado com sucesso!")
                    st.rerun()

        st.divider()
