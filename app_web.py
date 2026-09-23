import os
import re
import sqlite3
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st

# =========================================================
# 1. CONFIGURAÇÃO DA PÁGINA E DIRETÓRIOS
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

def validar_ncm(ncm):
    padrao = r"^\d{4}\.\d{2}\.\d{2}$"
    return re.match(padrao, ncm.strip()) is not None

def registrar_historico(tipo, item_nome, quantidade):
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO historico (data_hora, tipo, item_nome, quantidade)
            VALUES (?, ?, ?, ?)
        """, (datetime.now().strftime("%d/%m/%Y %H:%M:%S"), tipo, item_nome, quantidade))
        conn.commit()
        conn.close()
    except Exception:
        pass

# Função de busca simples de imagem que procura dentro da pasta uploads_conserto
def resolver_imagem(caminho_db):
    if not caminho_db:
        return None
    # 1. Se o caminho exato existir, usa ele
    if os.path.exists(caminho_db):
        return caminho_db
    
    # 2. Procura pelo nome do arquivo na pasta de uploads
    nome_arquivo = os.path.basename(caminho_db)
    caminho_direto = os.path.join(PASTA_UPLOADS, nome_arquivo)
    if os.path.exists(caminho_direto):
        return caminho_direto
    
    # 3. Tenta encontrar qualquer arquivo na pasta que contenha parte do nome (ex: peca_20260921)
    if os.path.exists(PASTA_UPLOADS):
         prefixo = nome_arquivo.split('.')[0][:15] if '.' in nome_arquivo else nome_arquivo[:15]
         for f in os.listdir(PASTA_UPLOADS):
             if prefixo and prefixo in f:
                 return os.path.join(PASTA_UPLOADS, f)
    return None

# =========================================================
# 2. INICIALIZAÇÃO DO BANCO DE DADOS
# =========================================================
def inicializar_banco():
    conn = conectar_banco()
    cursor = conn.cursor()
    
    # Tabela de Licenciamento
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    
    cursor.execute("SELECT valor FROM configuracoes WHERE chave='data_instalacao'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES ('data_instalacao', ?)", (datetime.now().strftime("%Y-%m-%d"),))

    # Tabela Estoque
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estoque (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cod TEXT,
            cod_ref TEXT,
            ncm TEXT NOT NULL,
            estante TEXT,
            prateleira TEXT,
            caixa TEXT,
            quanti INTEGER DEFAULT 0,
            preco REAL DEFAULT 0.0
        )
    """)

    # Tabela Consertos
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

    # Tabela Historico
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT,
            tipo TEXT,
            item_nome TEXT,
            quantidade INTEGER
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
                    st.success("Licença desbloqueada com sucesso!")
                    st.rerun()
                else:
                    st.error("Código Master incorreto!")
            return False
    return True

if not verificar_licenca():
    st.stop()

# =========================================================
# 4. TELA DE LOGIN
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
# 5. MENU LATERAL
# =========================================================
st.sidebar.title("🏢 Estoque Requipel")
st.sidebar.caption(f"Usuário: {st.session_state.get('usuario_logado', 'Admin')}")

if st.sidebar.button("🚪 Sair"):
    st.session_state["autenticado"] = False
    st.rerun()

st.sidebar.divider()

opcao = st.sidebar.radio(
    "Navegação:",
    [
        "📊 Visão Geral / Dashboard",
        "🛠️ Gestão de Consertos",
        "📦 Cadastrar Peça",
        "📜 Histórico (Logs)"
    ]
)

# =========================================================
# 6. DASHBOARD / VISÃO GERAL
# =========================================================
if opcao == "📊 Visão Geral / Dashboard":
    st.title("📊 Visão Geral do Estoque")
    
    conn = conectar_banco()
    df_est = pd.read_sql_query("SELECT * FROM estoque", conn)
    conn.close()

    st.dataframe(df_est, use_container_width=True)

# =========================================================
# 7. GESTÃO DE CONSERTOS
# =========================================================
elif opcao == "🛠️ Gestão de Consertos":
    st.title("🛠️ Gestão de Peças em Conserto / Manutenção")
    
    with st.expander("➕ Enviar Nova Peça para Conserto", expanded=False):
        with st.form("form_conserto_novo", clear_on_submit=True):
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                item_nome = st.text_input("Nome do Material / Peça *")
                cod_ref = st.text_input("Cód. Interno/REF")
                oficina = st.text_input("Oficina / Empresa *")
            with f_col2:
                num_nf = st.text_input("Nº da NF de Remessa")
                defeito = st.text_area("Descrição do Defeito")
            
            f_img1, f_img2 = st.columns(2)
            with f_img1:
                f_peca = st.file_uploader("Foto da Peça", type=["png", "jpg", "jpeg"])
            with f_img2:
                f_nf = st.file_uploader("Foto da NF", type=["png", "jpg", "jpeg"])
            
            if st.form_submit_button("🚀 Enviar para Conserto"):
                if not item_nome or not oficina:
                    st.error("Preencha o nome da peça e a oficina.")
                else:
                    p_peca = ""
                    p_nf = ""
                    time_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                    
                    if f_peca:
                        p_peca = os.path.join(PASTA_UPLOADS, f"peca_{time_str}_{f_peca.name}")
                        with open(p_peca, "wb") as f:
                            f.write(f_peca.getbuffer())
                    if f_nf:
                        p_nf = os.path.join(PASTA_UPLOADS, f"nf_{time_str}_{f_nf.name}")
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
                    registrar_historico("ENVIO_CONSERTO", item_nome, 1)
                    st.success("Enviado com sucesso!")
                    st.rerun()

    st.divider()

    conn = conectar_banco()
    # Traz todos os consertos que NÃO estejam marcados como 'Retornado'
    df_consertos = pd.read_sql_query("SELECT * FROM consertos WHERE status IS NULL OR status != 'Retornado' ORDER BY id DESC", conn)
    conn.close()

    if df_consertos.empty:
        st.info("Nenhuma peça em conserto no momento.")
    else:
        for idx, row in df_consertos.iterrows():
            col_img, col_detalhes, col_status = st.columns([1.5, 3, 1.5])
            
            with col_img:
                col_p, col_nf = st.columns(2)
                
                img_peca = resolver_imagem(row['caminho_foto_peca'])
                with col_p:
                    st.caption("📷 Foto da Peça")
                    if img_peca:
                        st.image(img_peca, use_container_width=True)
                    else:
                        st.info("Sem foto cadastrada")
                
                img_nf = resolver_imagem(row['caminho_foto_nf'])
                with col_nf:
                    st.caption("📄 Foto da NF")
                    if img_nf:
                        st.image(img_nf, use_container_width=True)
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
                    if st.button("Confirmar Retorno ao Estoque", key=f"ret_{row['id']}"):
                        conn = conectar_banco()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE consertos SET status = 'Retornado' WHERE id = ?", (row['id'],))
                        conn.commit()
                        conn.close()
                        registrar_historico("RETORNO_CONSERTO", row['item_nome'], 1)
                        st.success("Retorno registrado!")
                        st.rerun()

            st.divider()

# =========================================================
# 8. CADASTRO DE PEÇAS
# =========================================================
elif opcao == "📦 Cadastrar Peça":
    st.title("📦 Cadastrar Novo Material")
    
    with st.form("form_cadastro_original", clear_on_submit=True):
        nome = st.text_input("Nome do Material *")
        cod = st.text_input("Código Interno:")
        ref = st.text_input("Código de Referência:")
        ncm = st.text_input("NCM (Formato XXXX.XX.XX) *")
        preco = st.number_input("Preço (R$):", min_value=0.0, step=0.01)
        estante = st.text_input("Estante:")
        prateleira = st.text_input("Prateleira:")
        caixa = st.text_input("Caixa / Posição:")
        qtd = st.number_input("Quantidade Inicial:", min_value=0, step=1)

        btn_salvar = st.form_submit_button("💾 SALVAR E CADASTRAR OUTRO")

        if btn_salvar:
            if not nome:
                st.warning("O campo Nome do Material é obrigatório!")
            elif not ncm:
                st.error("O campo NCM é obrigatório!")
            elif not validar_ncm(ncm):
                st.error("Formato do NCM inválido! Utilize o padrão de 8 dígitos com pontos (ex: 8481.80.99).")
            else:
                conn = conectar_banco()
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        """
                        INSERT INTO estoque (nome, cod, cod_ref, ncm, estante, prateleira, caixa, quanti, preco)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            nome,
                            cod,
                            ref,
                            ncm.strip(),
                            estante,
                            prateleira,
                            caixa,
                            qtd,
                            preco,
                        ),
                    )
                    conn.commit()
                    registrar_historico("CADASTRO", nome, qtd)
                    st.success(f"Material '{nome}' cadastrado com sucesso! Os campos foram limpos.")
                except sqlite3.Error as e:
                    st.error(f"Erro ao salvar no banco: {e}")
                finally:
                    conn.close()

# =========================================================
# 9. HISTÓRICO
# =========================================================
elif opcao == "📜 Histórico (Logs)":
    st.title("📜 Histórico de Movimentações Gerais")

    conn = conectar_banco()
    df_hist = pd.read_sql_query(
        "SELECT data_hora AS 'Data e Hora', tipo AS 'Tipo Ação', item_nome AS Item, quantidade AS Quantidade FROM historico ORDER BY id DESC",
        conn,
    )
    conn.close()

    st.dataframe(df_hist, use_container_width=True)
