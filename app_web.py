import os
import re
import requests
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

# =========================================================
# 1. CONFIGURAÇÃO DA PÁGINA
# =========================================================
st.set_page_config(
    page_title="Estoque Requipel",
    page_icon="📦",
    layout="wide"
)

# Conexão com o Banco PostgreSQL no Supabase via Secrets
@st.cache_resource
def obter_engine():
    try:
        db_url = st.secrets["postgres"]["url"]
        return create_engine(db_url)
    except Exception as e:
        st.error(f"Erro ao conectar ao banco de dados: {e}")
        st.stop()

def validar_ncm(ncm):
    if not ncm:
        return False
    padrao = r"^\d{4}\.\d{2}\.\d{2}$"
    return re.match(padrao, ncm.strip()) is not None

def registrar_historico(tipo, item_nome, quantidade, obs=""):
    try:
        engine = obter_engine()
        with engine.begin() as conn:
            query = text("""
                INSERT INTO historico (data_hora, tipo, item_nome, quantidade, observacao, usuario)
                VALUES (:dh, :tp, :item, :qtd, :obs, :usr)
            """)
            conn.execute(query, {
                "dh": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "tp": tipo,
                "item": item_nome,
                "qtd": quantidade,
                "obs": obs,
                "usr": st.session_state.get('usuario_logado', 'Sistema')
            })
    except Exception:
        pass

# =========================================================
# UPLOAD DE IMAGENS DIRETO PARA O SUPABASE STORAGE
# =========================================================
def salvar_imagem_nuvem(file_obj, prefixo):
    if not file_obj:
        return ""
    try:
        sb_url = st.secrets["supabase"]["url"]
        sb_key = st.secrets["supabase"]["key"]
        
        url_storage = f"{sb_url}/storage/v1/object/uploads_conserto"
        
        time_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        nome_arquivo = f"{prefixo}_{time_str}_{file_obj.name.replace(' ', '_')}"
        
        headers = {
            "Authorization": f"Bearer {sb_key}",
            "apiKey": sb_key,
            "Content-Type": file_obj.type or "image/jpeg"
        }
        
        res = requests.post(f"{url_storage}/{nome_arquivo}", data=file_obj.getvalue(), headers=headers, timeout=10)
        
        if res.status_code in [200, 201]:
            return f"{sb_url}/storage/v1/object/public/uploads_conserto/{nome_arquivo}"
    except Exception:
        pass
    return ""

def excluir_conserto(id_conserto):
    engine = obter_engine()
    with engine.begin() as conn:
        res = conn.execute(text("SELECT item_nome FROM consertos WHERE id = :id"), {"id": id_conserto}).fetchone()
        if res:
            nome_item = res[0]
            conn.execute(text("DELETE FROM consertos WHERE id = :id"), {"id": id_conserto})
            registrar_historico("EXCLUSAO_CONSERTO", nome_item, 1, "Registro excluído manualmente")
            return True
    return False

# =========================================================
# 2. INICIALIZAÇÃO DAS TABELAS NO SUPABASE / POSTGRES
# =========================================================
def inicializar_banco():
    engine = obter_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS configuracoes (
                chave VARCHAR(255) PRIMARY KEY,
                valor TEXT
            )
        """))
        
        res = conn.execute(text("SELECT valor FROM configuracoes WHERE chave='data_instalacao'")).fetchone()
        if not res:
            conn.execute(text("INSERT INTO configuracoes (chave, valor) VALUES ('data_instalacao', :data)"), {"data": datetime.now().strftime("%Y-%m-%d")})

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS estoque (
                id SERIAL PRIMARY KEY,
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
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS consertos (
                id SERIAL PRIMARY KEY,
                item_nome TEXT NOT NULL,
                cod_ref TEXT,
                data_envio TEXT,
                oficina TEXT,
                num_nf TEXT,
                defeito TEXT,
                caminho_foto_peca TEXT,
                caminho_foto_nf TEXT,
                status TEXT DEFAULT 'Aguardando Coleta'
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS historico (
                id SERIAL PRIMARY KEY,
                data_hora TEXT,
                tipo TEXT,
                item_nome TEXT,
                quantidade INTEGER,
                observacao TEXT,
                usuario TEXT DEFAULT 'Sistema'
            )
        """))

inicializar_banco()

# =========================================================
# 3. VERIFICAÇÃO DE LICENÇA
# =========================================================
def verificar_licenca():
    engine = obter_engine()
    with engine.begin() as conn:
        unlocked = conn.execute(text("SELECT valor FROM configuracoes WHERE chave='master_unlocked'")).fetchone()
        if unlocked and unlocked[0] == '1':
            return True

        res = conn.execute(text("SELECT valor FROM configuracoes WHERE chave='data_instalacao'")).fetchone()
        
        if res:
            data_inst = datetime.strptime(res[0], "%Y-%m-%d")
            if (datetime.now() - data_inst).days > 90:
                st.error("🔒 LICENÇA EXPIRADA - Bloqueio de Segurança Ativado")
                codigo = st.text_input("Código Master:", type="password")
                if st.button("Desbloquear Sistema"):
                    if codigo == "202739":
                        conn.execute(text("INSERT INTO configuracoes (chave, valor) VALUES ('master_unlocked', '1') ON CONFLICT (chave) DO UPDATE SET valor = '1'"))
                        st.success("Licença desbloqueada com sucesso!")
                        st.rerun()
                    else:
                        st.error("Código Master incorreto!")
                return False
    return True

if not verificar_licenca():
    st.stop()

# =========================================================
# 4. AUTENTICAÇÃO E LOGIN
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
# 5. MENU LATERAL DE NAVEGAÇÃO
# =========================================================
st.sidebar.title("🏢 Estoque Requipel")
st.sidebar.caption(f"Usuário ativo: {st.session_state.get('usuario_logado', 'Admin')}")
st.sidebar.success("☁️ Conectado ao Supabase")

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
        "📜 Histórico (Logs)",
        "🔍 Consulta Rápida NCM"
    ]
)

# =========================================================
# MÓDULO 1: DASHBOARD
# =========================================================
if menu == "📊 Visão Geral / Dashboard":
    st.title("📊 Painel Geral do Estoque")
    
    engine = obter_engine()
    df_est = pd.read_sql("SELECT * FROM estoque", engine)
    df_cons = pd.read_sql("SELECT * FROM consertos WHERE status IS NULL OR status != 'Retornado'", engine)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total de Itens Cadastrados", len(df_est))
    m2.metric("Peças em Conserto / Coleta", len(df_cons))
    
    qtd_total = df_est['quanti'].sum() if not df_est.empty and 'quanti' in df_est.columns else 0
    m3.metric("Unidades em Estoque", int(qtd_total))
    
    valor_total = (df_est['quanti'] * df_est['preco']).sum() if not df_est.empty and 'preco' in df_est.columns else 0.0
    m4.metric("Valor do Estoque (R$)", f"R$ {valor_total:,.2f}")

    st.divider()

    col_g1, col_g2 = st.columns([1.8, 1])
    
    with col_g1:
        st.subheader("📦 Top 10 Itens com Maior Quantidade")
        if not df_est.empty and 'quanti' in df_est.columns and df_est['quanti'].sum() > 0:
            df_top = df_est.groupby('nome', as_index=False)['quanti'].sum()
            df_top = df_top.sort_values(by='quanti', ascending=True).tail(10)
            
            fig_bar = px.bar(
                df_top,
                x='quanti',
                y='nome',
                orientation='h',
                text='quanti',
                labels={'nome': 'Item / Material', 'quanti': 'Quantidade em Estoque'},
                color_discrete_sequence=['#1f77b4']
            )
            fig_bar.update_traces(textposition='outside')
            fig_bar.update_layout(
                yaxis={'categoryorder': 'total ascending', 'title': ''},
                xaxis_title="Quantidade",
                margin=dict(l=20, r=20, t=20, b=20),
                height=380
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Sem dados suficientes para gráficos.")

    with col_g2:
        st.subheader("📍 Resumo de Itens por Estante")
        if not df_est.empty and 'estante' in df_est.columns and df_est['estante'].notna().any():
            df_estante = df_est.groupby('estante', as_index=False).agg(
                Itens=('id', 'count'),
                Total_Unidades=('quanti', 'sum')
            ).rename(columns={'estante': 'Estante', 'Total_Unidades': 'Unidades Total'})
            
            df_estante['Estante'] = df_estante['Estante'].replace('', 'Não Informada')
            st.dataframe(df_estante, use_container_width=True, hide_index=True)
        else:
            st.info("Sem dados de localização por estante.")

    st.divider()
    st.subheader("📋 Tabela do Estoque Geral")
    
    busca = st.text_input("🔍 Pesquisar material por Nome, Código, Referência ou NCM:")
    if busca and not df_est.empty:
        df_exibir = df_est[
            df_est['nome'].astype(str).str.contains(busca, case=False, na=False) |
            df_est['cod'].astype(str).str.contains(busca, case=False, na=False) |
            df_est['cod_ref'].astype(str).str.contains(busca, case=False, na=False) |
            df_est['ncm'].astype(str).str.contains(busca, case=False, na=False)
        ]
    else:
        df_exibir = df_est

    st.dataframe(df_exibir, use_container_width=True)

# =========================================================
# MÓDULO 2: GESTÃO DE CONSERTOS
# =========================================================
elif menu == "🛠️ Gestão de Consertos":
    st.title("🛠️ Gestão de Peças em Conserto / Manutenção")
    
    tab_cad, tab_coleta, tab_manut, tab_ret = st.tabs([
        "➕ 1. Cadastrar Manutenção",
        "⏳ 2. Aguardando Coleta",
        "🛠️ 3. Em Manutenção (Oficina)",
        "✅ 4. Peças Retornadas"
    ])
    
    # TAB 1: CADASTRO
    with tab_cad:
        st.subheader("Cadastrar Nova Peça para Manutenção")
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
            
            if st.form_submit_button("💾 Cadastrar (Marcar 'Aguardando Coleta')"):
                if not item_nome or not oficina:
                    st.error("Preencha o Nome da Peça e a Oficina.")
                else:
                    url_p = salvar_imagem_nuvem(f_peca, "peca")
                    url_nf = salvar_imagem_nuvem(f_nf, "nf")

                    engine = obter_engine()
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO consertos (item_nome, cod_ref, data_envio, oficina, num_nf, defeito, caminho_foto_peca, caminho_foto_nf, status)
                            VALUES (:nome, :ref, :data, :oficina, :nf, :defeito, :peca, :fotof, 'Aguardando Coleta')
                        """), {
                            "nome": item_nome, "ref": cod_ref, "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                            "oficina": oficina, "nf": num_nf, "defeito": defeito, "peca": url_p, "fotof": url_nf
                        })
                    registrar_historico("CADASTRO_CONSERTO", item_nome, 1, f"Oficina: {oficina}")
                    st.success("Peça e imagens salvas com sucesso no Supabase!")
                    st.rerun()

    # TAB 2: AGUARDANDO COLETA
    with tab_coleta:
        st.subheader("⏳ Peças Aguardando Coleta para Ir à Oficina")
        engine = obter_engine()
        df_coleta = pd.read_sql("SELECT * FROM consertos WHERE status = 'Aguardando Coleta' OR status = 'Em espera de coleta' ORDER BY id DESC", engine)

        if df_coleta.empty:
            st.info("Nenhuma peça aguardando coleta no momento.")
        else:
            for idx, row in df_coleta.iterrows():
                col_img, col_detalhes, col_acao = st.columns([1.5, 3, 1.5])
                
                with col_img:
                    col_p, col_nf = st.columns(2)
                    with col_p:
                        st.caption("📷 Foto Peça")
                        if row['caminho_foto_peca']: st.image(row['caminho_foto_peca'], use_container_width=True)
                        else: st.info("Sem foto")
                    
                    with col_nf:
                        st.caption("📄 Foto NF")
                        if row['caminho_foto_nf']: st.image(row['caminho_foto_nf'], use_container_width=True)
                        else: st.info("Sem foto NF")

                with col_detalhes:
                    st.subheader(f"**{row['item_nome']}**")
                    st.write(f"**Cód. Interno/REF:** {row['cod_ref'] if row['cod_ref'] else 'N/A'}")
                    st.write(f"**Data Cadastro:** {row['data_envio']}")
                    st.write(f"**Oficina Destino:** {row['oficina']}")
                    st.write(f"**Nº NF:** {row['num_nf']}")
                    st.write(f"**Defeito:** {row['defeito']}")

                with col_acao:
                    st.warning("Status: Aguardando Coleta")
                    if st.button("🚚 Confirmar Coleta", key=f"col_{row['id']}"):
                        with engine.begin() as conn:
                            conn.execute(text("UPDATE consertos SET status = 'Em Conserto' WHERE id = :id"), {"id": row['id']})
                        registrar_historico("COLETADO_CONSERTO", row['item_nome'], 1, f"Oficina: {row['oficina']}")
                        st.success("Coleta confirmada!")
                        st.rerun()

                    if st.button("🗑️ Excluir Registro", key=f"del_col_{row['id']}", type="secondary"):
                        if excluir_conserto(row['id']):
                            st.success("Registro excluído!")
                            st.rerun()

                st.divider()

    # TAB 3: EM MANUTENÇÃO
    with tab_manut:
        st.subheader("🛠️ Peças em Manutenção na Oficina")
        engine = obter_engine()
        df_manut = pd.read_sql("SELECT * FROM consertos WHERE status = 'Em Conserto' OR status IS NULL ORDER BY id DESC", engine)

        if df_manut.empty:
            st.info("Nenhuma peça atualmente em manutenção na oficina.")
        else:
            for idx, row in df_manut.iterrows():
                col_img, col_detalhes, col_acao = st.columns([1.5, 3, 1.5])
                
                with col_img:
                    col_p, col_nf = st.columns(2)
                    with col_p:
                        st.caption("📷 Foto Peça")
                        if row['caminho_foto_peca']: st.image(row['caminho_foto_peca'], use_container_width=True)
                        else: st.info("Sem foto")
                    
                    with col_nf:
                        st.caption("📄 Foto NF")
                        if row['caminho_foto_nf']: st.image(row['caminho_foto_nf'], use_container_width=True)
                        else: st.info("Sem foto NF")

                with col_detalhes:
                    st.subheader(f"**{row['item_nome']}**")
                    st.write(f"**Cód. Interno/REF:** {row['cod_ref'] if row['cod_ref'] else 'N/A'}")
                    st.write(f"**Data de Envio:** {row['data_envio']}")
                    st.write(f"**Oficina / Empresa:** {row['oficina']}")
                    st.write(f"**Nº NF:** {row['num_nf']}")
                    st.write(f"**Defeito:** {row['defeito']}")

                with col_acao:
                    st.info("Status: Em Manutenção")
                    if st.button("✅ Confirmar Retorno ao Estoque", key=f"ret_{row['id']}"):
                        with engine.begin() as conn:
                            conn.execute(text("UPDATE consertos SET status = 'Retornado' WHERE id = :id"), {"id": row['id']})
                        registrar_historico("RETORNO_CONSERTO", row['item_nome'], 1, f"Oficina: {row['oficina']}")
                        st.success("Retorno registrado com sucesso!")
                        st.rerun()

                    if st.button("🗑️ Excluir Registro", key=f"del_man_{row['id']}", type="secondary"):
                        if excluir_conserto(row['id']):
                            st.success("Registro excluído!")
                            st.rerun()

                st.divider()

    # TAB 4: PEÇAS RETORNADAS
    with tab_ret:
        st.subheader("✅ Histórico de Peças Retornadas da Manutenção")
        engine = obter_engine()
        df_ret = pd.read_sql("SELECT * FROM consertos WHERE status = 'Retornado' ORDER BY id DESC", engine)

        if df_ret.empty:
            st.info("Nenhum histórico de retorno de peças registrado ainda.")
        else:
            st.dataframe(df_ret, use_container_width=True)

# =========================================================
# MÓDULO 3: MOVIMENTAÇÃO DE ESTOQUE
# =========================================================
elif menu == "📦 Movimentação de Estoque":
    st.title("📦 Movimentação de Entrada e Saída de Materiais")
    
    engine = obter_engine()
    df_estoque = pd.read_sql("SELECT id, nome, cod, cod_ref, quanti FROM estoque ORDER BY nome ASC", engine)

    if df_estoque.empty:
        st.warning("Nenhum material cadastrado para movimentar.")
    else:
        termo_busca = st.text_input("🔍 Buscar Peça por Nome, Código Interno ou Cód. Referência:")
        
        df_filtrado = df_estoque.copy()
        if termo_busca:
            df_filtrado = df_estoque[
                df_estoque['nome'].astype(str).str.contains(termo_busca, case=False, na=False) |
                df_estoque['cod'].astype(str).str.contains(termo_busca, case=False, na=False) |
                df_estoque['cod_ref'].astype(str).str.contains(termo_busca, case=False, na=False)
            ]
        
        if df_filtrado.empty:
            st.error("Nenhuma peça encontrada com o termo pesquisado.")
        else:
            opcoes_mat = {
                f"[{row['nome']}] - Cód: {row['cod'] if row['cod'] else 'N/A'} | REF: {row['cod_ref'] if row['cod_ref'] else 'N/A'} (Qtd: {row['quanti']}) - ID #{row['id']}": row['id'] 
                for idx, row in df_filtrado.iterrows()
            }
            
            mat_sel = st.selectbox("Selecione o Material Desejado:", list(opcoes_mat.keys()))
            mat_id = opcoes_mat[mat_sel]

            col1, col2 = st.columns(2)
            with col1:
                tipo_mov = st.radio("Tipo de Movimentação:", ["ENTRADA (Adicionar)", "SAÍDA (Remover)"])
                qtd_mov = st.number_input("Quantidade:", min_value=1, step=1)
            with col2:
                obs_mov = st.text_area("Observação / Destino / Motivo:")

            if st.button("🚀 Confirmar Movimentação"):
                with engine.begin() as conn:
                    res_mat = conn.execute(text("SELECT nome, quanti FROM estoque WHERE id = :id"), {"id": mat_id}).fetchone()
                    if res_mat:
                        nome_mat, qtd_atual = res_mat[0], res_mat[1]

                        if "SAÍDA" in tipo_mov and qtd_mov > qtd_atual:
                            st.error("Quantidade de saída é maior do que o estoque disponível!")
                        else:
                            nova_qtd = (qtd_atual + qtd_mov) if "ENTRADA" in tipo_mov else (qtd_atual - qtd_mov)
                            conn.execute(text("UPDATE estoque SET quanti = :qtd WHERE id = :id"), {"qtd": nova_qtd, "id": mat_id})
                            
                            tipo_str = "ENTRADA" if "ENTRADA" in tipo_mov else "SAÍDA"
                            registrar_historico(tipo_str, nome_mat, qtd_mov, obs_mov)
                            
                            st.success(f"Movimentação realizada! Novo estoque: {nova_qtd}")
                            st.rerun()

# =========================================================
# MÓDULO 4: CADASTRO E EDIÇÃO DE PEÇAS
# =========================================================
elif menu == "➕ Cadastrar / Editar Peças":
    st.title("➕ Gestão de Peças e Materiais")
    
    tab_cad, tab_edit = st.tabs(["Cadastrar Novo Material", "Editar / Excluir Existente"])
    
    # SUB-ABA 1: CADASTRO INDIVIDUAL
    with tab_cad:
        with st.form("form_cadastro_original", clear_on_submit=True):
            nome = st.text_input("Nome do Material *")
            c1, c2 = st.columns(2)
            with c1:
                cod = st.text_input("Código Interno:")
                ref = st.text_input("Código de Referência:")
                ncm = st.text_input("NCM (Formato XXXX.XX.XX) *", placeholder="Ex: 8481.80.99")
                preco = st.number_input("Preço (R$):", min_value=0.0, step=0.01)
            with c2:
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
                    st.error("Formato do NCM inválido! Utilize XXXX.XX.XX")
                else:
                    engine = obter_engine()
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO estoque (nome, cod, cod_ref, ncm, estante, prateleira, caixa, quanti, preco)
                            VALUES (:nome, :cod, :ref, :ncm, :estante, :prateleira, :caixa, :quanti, :preco)
                        """), {
                            "nome": nome, "cod": cod, "ref": ref, "ncm": ncm.strip(),
                            "estante": estante, "prateleira": prateleira, "caixa": caixa,
                            "quanti": qtd, "preco": preco
                        })
                    registrar_historico("CADASTRO", nome, qtd)
                    st.success(f"Material '{nome}' cadastrado no Supabase!")

    # SUB-ABA 2: EDIÇÃO INDIVIDUAL POR ID E FILTRO
    with tab_edit:
        engine = obter_engine()
        df_edit = pd.read_sql("SELECT * FROM estoque ORDER BY nome ASC", engine)

        if not df_edit.empty:
            busca_edit = st.text_input("🔍 Pesquisar Peça para Edição por Nome, Código Interno ou REF:")
            
            df_edit_filtrado = df_edit.copy()
            if busca_edit:
                df_edit_filtrado = df_edit[
                    df_edit['nome'].astype(str).str.contains(busca_edit, case=False, na=False) |
                    df_edit['cod'].astype(str).str.contains(busca_edit, case=False, na=False) |
                    df_edit['cod_ref'].astype(str).str.contains(busca_edit, case=False, na=False)
                ]

            if df_edit_filtrado.empty:
                st.warning("Nenhuma peça encontrada com os dados informados.")
            else:
                opcoes_materiais = {
                    f"[{row['nome']}] - Cód: {row['cod'] if row['cod'] else 'N/A'} | REF: {row['cod_ref'] if row['cod_ref'] else 'N/A'} | NCM: {row['ncm']} (ID #{row['id']})": row['id'] 
                    for _, row in df_edit_filtrado.iterrows()
                }
                mat_selecionado = st.selectbox("Selecione a peça exata para Editar:", list(opcoes_materiais.keys()))
                id_material = opcoes_materiais[mat_selecionado]
                
                row_e = df_edit[df_edit['id'] == id_material].iloc[0]

                with st.form(f"form_edicao_{id_material}"):
                    st.caption(f"✍️ Editando exclusivamente o registro ID #{id_material}")
                    enome = st.text_input("Nome", value=str(row_e['nome']))
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        ecod = st.text_input("Código Interno", value=str(row_e['cod']) if row_e['cod'] else "")
                        eref = st.text_input("Código de Referência (REF)", value=str(row_e['cod_ref']) if row_e['cod_ref'] else "")
                        encm = st.text_input("NCM Exclusivo desta Peça", value=str(row_e['ncm']) if row_e['ncm'] else "")
                        epreco = st.number_input("Preço", value=float(row_e['preco']) if row_e['preco'] else 0.0)
                    with ec2:
                        eestante = st.text_input("Estante", value=str(row_e['estante']) if row_e['estante'] else "")
                        eprat = st.text_input("Prateleira", value=str(row_e['prateleira']) if row_e['prateleira'] else "")
                        ecaixa = st.text_input("Caixa", value=str(row_e['caixa']) if row_e['caixa'] else "")
                        eqtd = st.number_input("Quantidade", value=int(row_e['quanti']) if row_e['quanti'] else 0)

                    b_edit = st.form_submit_button("💾 Salvar Alterações Apenas Nesta Peça")
                    if b_edit:
                        if not validar_ncm(encm):
                            st.error("Formato NCM inválido! Use XXXX.XX.XX")
                        else:
                            with engine.begin() as conn:
                                conn.execute(text("""
                                    UPDATE estoque 
                                    SET nome=:nome, cod=:cod, cod_ref=:ref, ncm=:ncm, estante=:est, prateleira=:prat, caixa=:caixa, quanti=:qtd, preco=:preco
                                    WHERE id=:id
                                """), {
                                    "nome": enome, "cod": ecod, "ref": eref, "ncm": encm,
                                    "est": eestante, "prat": eprat, "caixa": ecaixa,
                                    "qtd": eqtd, "preco": epreco, "id": id_material
                                })
                            registrar_historico("EDICAO", enome, eqtd, f"ID #{id_material} modificado")
                            st.success("Peça atualizada no banco em nuvem!")
                            st.rerun()

# =========================================================
# MÓDULO 5: HISTÓRICO (LOGS)
# =========================================================
elif menu == "📜 Histórico (Logs)":
    st.title("📜 Histórico de Movimentações e Logs")
    engine = obter_engine()
    df_hist = pd.read_sql("SELECT * FROM historico ORDER BY id DESC", engine)

    if df_hist.empty:
        st.info("Nenhuma movimentação registrada no histórico.")
    else:
        st.dataframe(df_hist, use_container_width=True)

# =========================================================
# MÓDULO 6: CONSULTA RÁPIDA NCM
# =========================================================
elif menu == "🔍 Consulta Rápida NCM":
    st.title("🔍 Consulta Rápida NCM")
    st.caption("Verifique as NCMs cadastradas na base do sistema.")
    
    engine = obter_engine()
    df_ncm = pd.read_sql("SELECT DISTINCT ncm, nome, cod_ref FROM estoque ORDER BY ncm ASC", engine)

    termo_ncm = st.text_input("Digite o número do NCM ou nome da peça:")
    if termo_ncm:
        df_ncm = df_ncm[
            df_ncm['ncm'].astype(str).str.contains(termo_ncm, case=False, na=False) |
            df_ncm['nome'].astype(str).str.contains(termo_ncm, case=False, na=False)
        ]

    st.dataframe(df_ncm, use_container_width=True)
