import os
import re
import sqlite3
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st

# =========================================================
# 1. CONFIGURAÇÃO DA PÁGINA E DIRETIÓRIOS
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
# 2. INICIALIZAÇÃO DO BANCO DE DADOS E TABELAS
# =========================================================
def inicializar_banco():
    conn = conectar_banco()
    cursor = conn.cursor()
    
    # Configurações e Licença
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    cursor.execute("SELECT valor FROM configuracoes WHERE chave='data_instalacao'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('data_instalacao', ?)", (datetime.now().strftime("%Y-%m-%d"),))

    # Tabela de Peças
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

    # Tabela de Consertos
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

    # Tabela de Histórico
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
# 3. VERIFICAÇÃO DE LICENÇA (90 DIAS)
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
                    st.success("Licença validada com sucesso!")
                    st.rerun()
                else:
                    st.error("Código incorreto.")
            return False
    return True

if not verificar_licenca():
    st.stop()

# =========================================================
# 4. TELA DE LOGIN
# =========================================================
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

def tela_login():
    st.markdown("<h1 style='text-align: center;'>🔑 Acesso ao Sistema - Estoque Requipel</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login_form"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            btn_entrar = st.form_submit_button("ENTRAR")
            if btn_entrar:
                if (usuario.lower() == "admin" and senha == "1234") or (usuario.lower() == "almox" and senha == "rqp123"):
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_logado"] = usuario
                    st.success("Acesso liberado!")
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos.")

if not st.session_state["autenticado"]:
    tela_login()
    st.stop()

# =========================================================
# 5. MENU LATERAL
# =========================================================
st.sidebar.title("🏢 Almoxarifado Requipel")
st.sidebar.caption(f"Usuário ativo: {st.session_state.get('usuario_logado', 'Admin')}")

if st.sidebar.button("🚪 Sair / Logout"):
    st.session_state["autenticado"] = False
    st.rerun()

st.sidebar.divider()

menu = st.sidebar.radio(
    "Navegação do Sistema:",
    [
        "📊 Visão Geral / Dashboard",
        "🛠️ Gestão de Consertos",
        "📦 Movimentação de Estoque",
        "➕ Cadastrar / Editar Peças",
        "📜 Histórico Geral",
        "🔍 Consulta Rápida NCM"
    ]
)

# =========================================================
# MÓDULO 1: DASHBOARD
# =========================================================
if menu == "📊 Visão Geral / Dashboard":
    st.title("📊 Painel Geral do Almoxarifado")
    
    conn = conectar_banco()
    df_pecas = pd.read_sql_query("SELECT * FROM pecas", conn)
    df_consertos = pd.read_sql_query("SELECT * FROM consertos WHERE status != 'Retornado'", conn)
    conn.close()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total de Itens Cadastrados", len(df_pecas))
    m2.metric("Peças em Conserto / Espera", len(df_consertos))
    
    qtd_total = df_pecas['quantidade'].sum() if not df_pecas.empty else 0
    m3.metric("Quantidade Total em Estoque", int(qtd_total))
    
    itens_criticos = df_pecas[df_pecas['quantidade'] <= df_pecas['qtd_minima']] if not df_pecas.empty else pd.DataFrame()
    m4.metric("Itens com Estoque Baixo", len(itens_criticos))

    st.divider()

    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("📦 Top 10 Itens com Maior Quantidade")
        if not df_pecas.empty and df_pecas['quantidade'].sum() > 0:
            top_pecas = df_pecas.sort_values(by='quantidade', ascending=False).head(10)
            fig_bar = px.bar(top_pecas, x='nome', y='quantidade', labels={'nome': 'Item', 'quantidade': 'Qtd'}, text_auto=True, color='quantidade')
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Sem dados suficientes para gráficos.")

    with col_chart2:
        st.subheader("📁 Distribuição por Categoria")
        if not df_pecas.empty and 'categoria' in df_pecas.columns and df_pecas['categoria'].notna().any():
            df_cat = df_pecas['categoria'].value_counts().reset_index()
            df_cat.columns = ['Categoria', 'Quantidade']
            fig_pie = px.pie(df_cat, names='Categoria', values='Quantidade', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Sem dados de categoria.")

    st.divider()
    st.subheader("📋 Tabela Geral do Estoque")
    
    search = st.text_input("🔍 Pesquisar item por Nome, Código ou NCM:")
    if search and not df_pecas.empty:
        df_exibir = df_pecas[
            df_pecas['nome'].astype(str).str.contains(search, case=False, na=False) |
            df_pecas['codigo'].astype(str).str.contains(search, case=False, na=False) |
            df_pecas['ncm'].astype(str).str.contains(search, case=False, na=False)
        ]
    else:
        df_exibir = df_pecas

    st.dataframe(df_exibir, use_container_width=True)

# =========================================================
# MÓDULO 2: GESTÃO DE CONSERTOS
# =========================================================
elif menu == "🛠️ Gestão de Consertos":
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
                defeito = st.text_area("Descrição detalhada do Defeito")
            
            f_img1, f_img2 = st.columns(2)
            with f_img1:
                f_peca = st.file_uploader("Foto da Peça", type=["png", "jpg", "jpeg"])
            with f_img2:
                f_nf = st.file_uploader("Foto da Nota Fiscal", type=["png", "jpg", "jpeg"])
            
            submetido = st.form_submit_button("🚀 Confirmar Envio para Conserto")
            
            if submetido:
                if not item_nome or not oficina:
                    st.error("Por favor, preencha o Nome do Item e a Oficina/Empresa.")
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
                    
                    cursor.execute("""
                        INSERT INTO historico (data_hora, tipo, item_nome, quantidade, observacao, usuario)
                        VALUES (?, 'ENVIO_CONSERTO', ?, 1, ?, ?)
                    """, (datetime.now().strftime("%d/%m/%Y %H:%M:%S"), item_nome, f"Enviado para: {oficina} | NF: {num_nf}", st.session_state.get('usuario_logado', 'Admin')))
                    
                    conn.commit()
                    conn.close()
                    st.success("Peça enviada para conserto com sucesso!")
                    st.rerun()

    st.divider()

    conn = conectar_banco()
    df_consertos = pd.read_sql_query("SELECT * FROM consertos WHERE status != 'Retornado' ORDER BY id DESC", conn)
    conn.close()

    if df_consertos.empty:
        st.info("Nenhuma peça em conserto ou aguardando coleta no momento.")
    else:
        st.write(f"### Peças em Manutenção ({len(df_consertos)})")
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
                st.write(f"**Defeito Informado:** {row['defeito']}")

            with col_status:
                opcoes_status = ["Em Conserto", "Em espera de coleta"]
                status_atual = row['status'] if row['status'] in opcoes_status else "Em Conserto"
                
                novo_status = st.selectbox(
                    "Status Atual do Item:",
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
                    st.write("Confirmar que esta peça retornou da oficina para o estoque?")
                    if st.button("Confirmar Retorno ao Estoque", key=f"ret_{row['id']}"):
                        conn = conectar_banco()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE consertos SET status = 'Retornado' WHERE id = ?", (row['id'],))
                        
                        cursor.execute("""
                            INSERT INTO historico (data_hora, tipo, item_nome, quantidade, observacao, usuario)
                            VALUES (?, 'RETORNO_CONSERTO', ?, 1, ?, ?)
                        """, (datetime.now().strftime("%d/%m/%Y %H:%M:%S"), row['item_nome'], f"Retornou da oficina: {row['oficina']}", st.session_state.get('usuario_logado', 'Admin')))
                        
                        conn.commit()
                        conn.close()
                        st.success("Retorno registrado com sucesso!")
                        st.rerun()

            st.divider()

# =========================================================
# MÓDULO 3: MOVIMENTAÇÃO DE ESTOQUE
# =========================================================
elif menu == "📦 Movimentação de Estoque":
    st.title("📦 Movimentação de Entrada e Saída de Peças")
    
    conn = conectar_banco()
    df_pecas = pd.read_sql_query("SELECT id, codigo, nome, quantidade FROM pecas ORDER BY nome ASC", conn)
    conn.close()

    if df_pecas.empty:
        st.warning("Nenhuma peça cadastrada para movimentar.")
    else:
        opcoes_pecas = {f"{row['codigo']} - {row['nome']} (Estoque: {row['quantidade']})": row['id'] for idx, row in df_pecas.iterrows()}
        peca_selecionada = st.selectbox("Selecione a Peça:", list(opcoes_pecas.keys()))
        peca_id = opcoes_pecas[peca_selecionada]

        col1, col2 = st.columns(2)
        with col1:
            tipo_mov = st.radio("Tipo de Movimentação:", ["ENTRADA (Adicionar)", "SAÍDA (Remover)"])
            qtd_mov = st.number_input("Quantidade:", min_value=1, step=1)
        with col2:
            obs_mov = st.text_area("Observação / Justificativa:")

        if st.button("🚀 Confirmar Movimentação"):
            conn = conectar_banco()
            cursor = conn.cursor()
            
            cursor.execute("SELECT nome, quantidade FROM pecas WHERE id = ?", (peca_id,))
            nome_item, qtd_atual = cursor.fetchone()

            if "SAÍDA" in tipo_mov and qtd_mov > qtd_atual:
                st.error("Quantidade de saída maior do que o estoque disponível!")
                conn.close()
            else:
                nova_qtd = (qtd_atual + qtd_mov) if "ENTRADA" in tipo_mov else (qtd_atual - qtd_mov)
                cursor.execute("UPDATE pecas SET quantidade = ? WHERE id = ?", (nova_qtd, peca_id))
                
                tipo_hist = "ENTRADA" if "ENTRADA" in tipo_mov else "SAÍDA"
                cursor.execute("""
                    INSERT INTO historico (data_hora, tipo, item_nome, quantidade, observacao, usuario)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (datetime.now().strftime("%d/%m/%Y %H:%M:%S"), tipo_hist, nome_item, qtd_mov, obs_mov, st.session_state.get('usuario_logado', 'Admin')))
                
                conn.commit()
                conn.close()
                st.success(f"Movimentação realizada com sucesso! Novo estoque: {nova_qtd}")
                st.rerun()

# =========================================================
# MÓDULO 4: CADASTRO / EDIÇÃO COM NCM MANDATÓRIO
# =========================================================
elif menu == "➕ Cadastrar / Editar Peças":
    st.title("➕ Cadastrar e Editar Peças do Estoque")
    
    tab_cad, tab_edit = st.tabs(["Nova Peça", "Editar / Excluir Peça Existente"])
    
    with tab_cad:
        with st.form("form_cadastro_peca", clear_on_submit=True):
            st.subheader("Cadastro de Nova Peça")
            c1, c2 = st.columns(2)
            with c1:
                codigo = st.text_input("Código Único do Item *")
                nome = st.text_input("Nome / Descrição da Peça *")
                quantidade = st.number_input("Quantidade Inicial", min_value=0, step=1)
                qtd_minima = st.number_input("Quantidade Mínima de Segurança", min_value=1, value=1)
            with c2:
                ncm = st.text_input("NCM Mandatory (Formato: XXXX.XX.XX) *", placeholder="Ex: 8483.40.10")
                categoria = st.text_input("Categoria (Ex: Elétrica, Mecânica)")
                localizacao = st.text_input("Prateleira / Posição")
                valor_un = st.number_input("Valor Unitário (R$)", min_value=0.0, format="%.2f")

            btn_cad = st.form_submit_button("💾 Salvar Peça no Estoque")
            
            if btn_cad:
                padrao_ncm = r"^\d{4}\.\d{2}\.\d{2}$"
                if not codigo or not nome or not ncm:
                    st.error("Por favor, preencha todos os campos obrigatórios (*).")
                elif not re.match(padrao_ncm, ncm):
                    st.error("❌ Formato de NCM Inválido! O NCM deve seguir o formato exato XXXX.XX.XX (exemplo: 8483.40.10).")
                else:
                    try:
                        conn = conectar_banco()
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO pecas (codigo, nome, quantidade, ncm, categoria, localizacao, qtd_minima, valor_unitario)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (codigo, nome, quantidade, ncm, categoria, localizacao, qtd_minima, valor_un))
                        
                        cursor.execute("""
                            INSERT INTO historico (data_hora, tipo, item_nome, quantidade, observacao, usuario)
                            VALUES (?, 'CADASTRO', ?, ?, ?, ?)
                        """, (datetime.now().strftime("%d/%m/%Y %H:%M:%S"), nome, quantidade, f"NCM: {ncm}", st.session_state.get('usuario_logado', 'Admin')))
                        
                        conn.commit()
                        conn.close()
                        st.success(f"Peça '{nome}' cadastrada com sucesso!")
                    except sqlite3.IntegrityError:
                        st.error("Já existe uma peça cadastrada com este mesmo Código!")

    with tab_edit:
        conn = conectar_banco()
        df_pecas = pd.read_sql_query("SELECT * FROM pecas ORDER BY nome ASC", conn)
        conn.close()

        if not df_pecas.empty:
            item_edit = st.selectbox("Selecione a peça para editar:", df_pecas['nome'].tolist())
            row_edit = df_pecas[df_pecas['nome'] == item_edit].iloc[0]

            with st.form("form_edicao"):
                e1, e2 = st.columns(2)
                with e1:
                    novo_codigo = st.text_input("Código", value=str(row_edit['codigo']))
                    novo_nome = st.text_input("Nome", value=str(row_edit['nome']))
                    nova_cat = st.text_input("Categoria", value=str(row_edit['categoria']))
                with e2:
                    novo_ncm = st.text_input("NCM", value=str(row_edit['ncm']))
                    nova_loc = st.text_input("Localização", value=str(row_edit['localizacao']))
                    nova_min = st.number_input("Qtd Mínima", value=int(row_edit['qtd_minima']))

                btn_salvar_edit = st.form_submit_button("Atualizar Dados")
                
                if btn_salvar_edit:
                    padrao_ncm = r"^\d{4}\.\d{2}\.\d{2}$"
                    if not re.match(padrao_ncm, novo_ncm):
                        st.error("Formato NCM inválido! Use XXXX.XX.XX")
                    else:
                        conn = conectar_banco()
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE pecas SET codigo=?, nome=?, ncm=?, categoria=?, localizacao=?, qtd_minima=?
                            WHERE id=?
                        """, (novo_codigo, novo_nome, novo_ncm, nova_cat, nova_loc, nova_min, row_edit['id']))
                        conn.commit()
                        conn.close()
                        st.success("Peça atualizada com sucesso!")
                        st.rerun()

# =========================================================
# MÓDULO 5: HISTÓRICO GERAL
# =========================================================
elif menu == "📜 Histórico Geral":
    st.title("📜 Histórico Geral de Movimentações")
    
    conn = conectar_banco()
    df_hist = pd.read_sql_query(
        "SELECT data_hora AS 'Data e Hora', tipo AS 'Tipo Ação', item_nome AS 'Item', quantidade AS 'Qtd', observacao AS 'Observação', usuario AS 'Usuário' FROM historico ORDER BY id DESC",
        conn
    )
    conn.close()

    if not df_hist.empty:
        st.dataframe(df_hist, use_container_width=True)
    else:
        st.info("Nenhuma movimentação registrada no histórico.")

# =========================================================
# MÓDULO 6: CONSULTA NCM
# =========================================================
elif menu == "🔍 Consulta Rápida NCM":
    st.title("🔍 Consulta Rápida de NCMs no Estoque")
    
    conn = conectar_banco()
    df_ncm = pd.read_sql_query("SELECT codigo AS 'Código', nome AS 'Peça', ncm AS 'NCM Cadastrado', categoria AS 'Categoria' FROM pecas", conn)
    conn.close()

    if not df_ncm.empty:
        st.dataframe(df_ncm, use_container_width=True)
    else:
        st.info("Nenhuma peça para consultar NCM.")
