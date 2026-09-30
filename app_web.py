import os
import re
import io
import requests
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

# Bibliotecas para geração de PDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

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

# Funcao auxiliar para gerar o PDF formatado de Solicitacao de Compras
def gerar_pdf_compras(df_itens):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()

    # Estilos customizados
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=16,
        leading=20,
        alignment=1, # Centralizado
        textColor=colors.HexColor("#1E3A8A")
    )
    
    sub_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontSize=10,
        leading=12,
        alignment=1,
        textColor=colors.gray
    )

    body_style = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontSize=9,
        leading=11
    )

    # Cabeçalho do Documento
    story.append(Paragraph("<b>REQUI PEL - SOLICITAÇÃO DE COMPRAS DE ESTOQUE</b>", title_style))
    story.append(Spacer(1, 4))
    data_str = datetime.now().strftime("%d/%m/%Y - %H:%M")
    solicitante = st.session_state.get('usuario_logado', 'Almoxarifado')
    story.append(Paragraph(f"Data de Emissão: {data_str} | Solicitante: {solicitante}", sub_style))
    story.append(Spacer(1, 15))

    # Tabela de Itens
    dados_tabela = [["Código / REF", "Descrição da Peça / Material", "NCM", "Est. Atual", "Status/Crítico"]]
    
    for _, row in df_itens.iterrows():
        cod_ref_str = f"Cód: {row['cod'] if row['cod'] else 'N/A'}\nREF: {row['cod_ref'] if row['cod_ref'] else 'N/A'}"
        nome_str = str(row['nome'])
        ncm_str = str(row['ncm']) if row['ncm'] else 'N/A'
        qtd_str = str(int(row['quanti']))
        critico_str = "🚨 CRÍTICO" if row['critico'] else "⚠️ Baixo Estoque"

        dados_tabela.append([
            Paragraph(cod_ref_str, body_style),
            Paragraph(nome_str, body_style),
            Paragraph(ncm_str, body_style),
            Paragraph(qtd_str, body_style),
            Paragraph(critico_str, body_style)
        ])

    tabela = Table(dados_tabela, colWidths=[100, 240, 75, 55, 80])
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#F9FAFB")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    story.append(tabela)
    story.append(Spacer(1, 20))
    story.append(Paragraph("<b>Observações para o Setor de Compras:</b> Documento gerado automaticamente pelo Sistema de Estoque Requipel.", sub_style))

    doc.build(story)
    buffer.seek(0)
    return buffer

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

# Dados do Inventário do Excel para Carga Inicial Automática (Sem marca)
DADOS_EXCEL_INICIAL = [
    (1, "Manômetro pressão"),
    (2, "Medidor de pressão"),
    (3, "Medidor de distância"),
    (4, "Regulador de argônio"),
    (5, "Terminais e adaptadores"),
    (6, "Pneumática vermelha"),
    (7, "Pneumática amarela"),
    (8, "Alicate hidráulico"),
    (9, "Pistola de ponto vermelha"),
    (10, "Pistola de ponto preta"),
    (11, "Paquímetro digital"),
    (12, "Paquímetro normal"),
    (13, "Flangeador"),
    (14, "Medidor com base"),
    (15, "Hand set zapi c/ cabos"),
    (16, "Hand set curtis c/ cabos"),
    (17, "Hand set voltex c/ cabos"),
    (18, "Notebook"),
    (20, "Tirador de solda"),
    (21, "Ferro de solda"),
    (22, "Torquímetro laranja"),
    (23, "Torquímetro preto"),
    (24, "Extrator pequeno"),
    (25, "Saca filtro"),
    (26, "Alicate amperímetro"),
    (27, "Torquesa"),
    (28, "Extrator grande"),
    (29, "Cabo de bateria / carregar"),
    (30, "Engates rápido mandril"),
    (31, "Jogo de retífica"),
    (32, "Furadeira impacto"),
    (33, "Furadeira impacto"),
    (34, "Lixadeira"),
    (35, "Jogo de cachimbo pesada"),
    (36, "Manômetro"),
    (37, "Manômetro hidráulico"),
    (38, "Lava jato"),
    (39, "Carregador de bateria"),
    (40, "Solda caneta"),
    (40, "Lixadeira grande"),
    (41, "SCHWEERS"),
    (42, "SCHWEERS MENOR"),
    (43, "Bico de encher pneu"),
    (44, "Saca filtro"),
    (45, "Compressor amarelo"),
    (46, "Vela / Tela fibra de vidro 50 metros"),
    (47, "Lupa"),
    (48, "Talha")
]

# =========================================================
# 2. INICIALIZAÇÃO E MIGRAÇÃO DAS TABELAS NO SUPABASE
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
                preco REAL DEFAULT 0.0,
                critico BOOLEAN DEFAULT FALSE
            )
        """))

        conn.execute(text("""
            ALTER TABLE estoque ADD COLUMN IF NOT EXISTS critico BOOLEAN DEFAULT FALSE;
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
            CREATE TABLE IF NOT EXISTS ferramentas_especiais (
                id SERIAL PRIMARY KEY,
                numero INTEGER,
                ferramenta TEXT NOT NULL,
                status TEXT DEFAULT 'DISPONIVEL',
                responsavel TEXT,
                data_retirada TEXT,
                historico_devolucao TEXT
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
st.sidebar.success("☁ Conectado ao Supabase")

if st.sidebar.button("🚪 Sair / Logout"):
    st.session_state["autenticado"] = False
    st.rerun()

st.sidebar.divider()

menu = st.sidebar.radio(
    "Navegação do Sistema:",
    [
        "📊 Visão Geral / Dashboard",
        "🧰 Ferramentas Especiais",
        "🛠 Gestão de Consertos",
        "📦 Movimentação de Estoque",
        "🚨 Peças Críticas e Pouco Estoque",
        "➕ Cadastrar / Editar Peças",
        "📜 Histórico (Logs)"
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

    df_criticos_zerados = pd.DataFrame()
    qtd_criticos_zerados = 0
    if not df_est.empty and 'critico' in df_est.columns:
        df_criticos_zerados = df_est[(df_est['critico'] == True) & (df_est['quanti'] == 0)]
        qtd_criticos_zerados = len(df_criticos_zerados)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total de Itens Cadastrados", len(df_est))
    m2.metric("Peças em Conserto / Coleta", len(df_cons))
    
    qtd_total = df_est['quanti'].sum() if not df_est.empty and 'quanti' in df_est.columns else 0
    m3.metric("Unidades em Estoque", int(qtd_total))
    
    valor_total = (df_est['quanti'] * df_est['preco']).sum() if not df_est.empty and 'preco' in df_est.columns else 0.0
    m4.metric("Valor do Estoque (R$)", f"R$ {valor_total:,.2f}")

    m5.metric("🚨 Itens Críticos Zerados", qtd_criticos_zerados)

    if not df_criticos_zerados.empty:
        st.error(f"⚠️ **ALERTA DE REPOSIÇÃO URGENTE:** Há {qtd_criticos_zerados} item(ns) marcado(s) como CRÍTICO com quantidade ZERO em estoque!")
        st.dataframe(
            df_criticos_zerados[['nome', 'cod', 'cod_ref', 'estante', 'prateleira', 'caixa']],
            use_container_width=True,
            hide_index=True
        )

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
# MÓDULO 2: FERRAMENTAS ESPECIAIS
# =========================================================
elif menu == "🧰 Ferramentas Especiais":
    st.title("🧰 Controle de Inventário de Ferramentas Especiais")
    st.caption("Acompanhe e controle a retirada e devolução de ferramentas especiais por colaborador.")

    tab_painel_ferr, tab_cad_ferr = st.tabs([
        "🧰 Painel de Ferramentas",
        "➕ Cadastrar Nova Ferramenta"
    ])

    engine = obter_engine()

    with tab_painel_ferr:
        df_ferr = pd.read_sql("SELECT * FROM ferramentas_especiais ORDER BY numero ASC, id ASC", engine)

        if df_ferr.empty:
            st.warning("Nenhuma ferramenta cadastrada no banco de dados.")
            if st.button("📥 Importar Lista Automática de Ferramentas (Tabela Excel)"):
                with engine.begin() as conn:
                    for num, fer in DADOS_EXCEL_INICIAL:
                        conn.execute(text("""
                            INSERT INTO ferramentas_especiais (numero, ferramenta, status)
                            VALUES (:num, :fer, 'DISPONIVEL')
                        """), {"num": num, "fer": fer})
                st.success("Lista de Ferramentas cadastrada com sucesso!")
                st.rerun()
        else:
            total_f = len(df_ferr)
            em_uso_f = len(df_ferr[df_ferr['status'] == 'EM_USO'])
            disp_f = total_f - em_uso_f

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("Total de Ferramentas", total_f)
            mc2.metric("✅ Disponíveis no Estoque", disp_f)
            mc3.metric("🔴 Empréstimos Ativos (Fora)", em_uso_f)

            st.divider()

            f_col1, f_col2 = st.columns([2, 1])
            with f_col1:
                busca_f = st.text_input("🔍 Pesquisar Ferramenta por Nome ou Nº:")
            with f_col2:
                filtro_status = st.selectbox("Filtrar por Status:", ["Todas", "Apenas Disponíveis", "Apenas Em Uso (Retiradas)"])

            df_exib = df_ferr.copy()
            
            if busca_f:
                df_exib = df_exib[
                    df_exib['ferramenta'].astype(str).str.contains(busca_f, case=False, na=False) |
                    df_exib['numero'].astype(str).str.contains(busca_f, case=False, na=False)
                ]
            
            if filtro_status == "Apenas Disponíveis":
                df_exib = df_exib[df_exib['status'] == 'DISPONIVEL']
            elif filtro_status == "Apenas Em Uso (Retiradas)":
                df_exib = df_exib[df_exib['status'] == 'EM_USO']

            st.markdown("### 📋 Caixinhas de Ferramentas")

            if df_exib.empty:
                st.info("Nenhuma ferramenta encontrada para a busca.")
            else:
                cols = st.columns(3)
                for idx, (_, row) in enumerate(df_exib.iterrows()):
                    col_atual = cols[idx % 3]
                    
                    with col_atual:
                        status_is_uso = (row['status'] == 'EM_USO')
                        
                        with st.container(border=True):
                            st.subheader(f"#{row['numero']} - {row['ferramenta']}")

                            if status_is_uso:
                                st.error("🔴 **FORA DE ESTOQUE (EM USO)**")
                                st.markdown(f"👤 **Com:** `{row['responsavel']}`")
                                st.markdown(f"🕒 **Retirado em:** {row['data_retirada']}")
                                
                                dev_por = st.text_input("Quem devolveu?", key=f"dev_usr_{row['id']}", placeholder="Nome do responsável")
                                if st.button("📥 Registrar Devolução", key=f"btn_dev_{row['id']}", type="primary"):
                                    nome_dev = dev_por.strip() if dev_por else row['responsavel']
                                    dt_agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                    obs_hist = f"Devolvido por: {nome_dev} em {dt_agora}"
                                    
                                    with engine.begin() as conn:
                                        conn.execute(text("""
                                            UPDATE ferramentas_especiais 
                                            SET status='DISPONIVEL', responsavel=NULL, data_retirada=NULL, historico_devolucao=:hist
                                            WHERE id=:id
                                        """), {"hist": obs_hist, "id": row['id']})
                                    
                                    registrar_historico("DEVOLUCAO_FERRAMENTA", row['ferramenta'], 1, f"Devolvido por: {nome_dev}")
                                    st.success(f"Devolução de #{row['numero']} registrada!")
                                    st.rerun()

                            else:
                                st.success("✅ **DISPONÍVEL NO ESTOQUE**")
                                usr_pegou = st.text_input("Quem está pegando?", key=f"peg_usr_{row['id']}", placeholder="Nome de quem retirou")
                                if st.button("📤 Registrar Saída", key=f"btn_saida_{row['id']}"):
                                    if not usr_pegou:
                                        st.warning("Informe o nome de quem está retirando a ferramenta!")
                                    else:
                                        dt_agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                                        with engine.begin() as conn:
                                            conn.execute(text("""
                                                UPDATE ferramentas_especiais 
                                                SET status='EM_USO', responsavel=:resp, data_retirada=:dt
                                                WHERE id=:id
                                            """), {"resp": usr_pegou.strip(), "dt": dt_agora, "id": row['id']})
                                        
                                        registrar_historico("RETIRADA_FERRAMENTA", row['ferramenta'], 1, f"Retirado por: {usr_pegou.strip()}")
                                        st.success(f"Empréstimo para {usr_pegou.strip()} registrado!")
                                        st.rerun()

    # ABA PARA CADASTRAR NOVAS FERRAMENTAS ESPECIAIS
    with tab_cad_ferr:
        st.subheader("➕ Cadastrar Nova Ferramenta Especial no Inventário")
        with st.form("form_cad_nova_ferramenta", clear_on_submit=True):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                num_ferr = st.number_input("Número de Identificação (#)", min_value=1, step=1)
            with col_f2:
                nome_ferr = st.text_input("Nome / Descrição da Ferramenta *")

            btn_cad_f = st.form_submit_button("💾 SALVAR FERRAMENTA")

            if btn_cad_f:
                if not nome_ferr:
                    st.warning("O nome da ferramenta é obrigatório!")
                else:
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO ferramentas_especiais (numero, ferramenta, status)
                            VALUES (:num, :fer, 'DISPONIVEL')
                        """), {"num": num_ferr, "fer": nome_ferr.strip()})
                    
                    registrar_historico("CADASTRO_FERRAMENTA", nome_ferr.strip(), 1, f"Número: #{num_ferr}")
                    st.success(f"Ferramenta #{num_ferr} - '{nome_ferr}' cadastrada com sucesso!")
                    st.rerun()

# =========================================================
# MÓDULO 3: GESTÃO DE CONSERTOS
# =========================================================
elif menu == "🛠 Gestão de Consertos":
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
# MÓDULO 4: MOVIMENTAÇÃO DE ESTOQUE
# =========================================================
elif menu == "📦 Movimentação de Estoque":
    st.title("📦 Movimentação de Entrada e Saída de Materiais")
    
    engine = obter_engine()
    # Consulta incluindo os campos de localização da peça
    df_estoque = pd.read_sql("SELECT id, nome, cod, cod_ref, quanti, estante, prateleira, caixa FROM estoque ORDER BY nome ASC", engine)

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

            # Obter os dados completos da peça selecionada para mostrar a localização
            dados_peca = df_filtrado[df_filtrado['id'] == mat_id].iloc[0]

            # Exibição visual destacada da localização da peça
            estante_info = dados_peca['estante'] if pd.notna(dados_peca['estante']) and dados_peca['estante'] else "Não Inf."
            prat_info = dados_peca['prateleira'] if pd.notna(dados_peca['prateleira']) and dados_peca['prateleira'] else "Não Inf."
            caixa_info = dados_peca['caixa'] if pd.notna(dados_peca['caixa']) and dados_peca['caixa'] else "Não Inf."

            st.info(f"""
            📍 **Localização no Estoque:**  
            * **Estante:** `{estante_info}` | **Prateleira:** `{prat_info}` | **Caixa/Posição:** `{caixa_info}`  
            📦 **Quantidade Atual Disponível:** `{int(dados_peca['quanti'])} unidades`
            """)

            st.divider()

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
# MÓDULO 5: PEÇAS CRÍTICAS E POUCO ESTOQUE (COM BOTÃO DE DOWNLOAD PDF/EXCEL)
# =========================================================
elif menu == "🚨 Peças Críticas e Pouco Estoque":
    st.title("🚨 Monitoramento de Peças Importantes e Baixo Estoque")
    st.caption("Acompanhe peças marcadas como prioritárias ou com nível de saldo abaixo do limite de segurança.")
    
    engine = obter_engine()
    df_bc = pd.read_sql("SELECT * FROM estoque ORDER BY quanti ASC, nome ASC", engine)

    if df_bc.empty:
        st.info("Nenum material cadastrado na base de dados.")
    else:
        c_filtro1, c_filtro2 = st.columns(2)
        with c_filtro1:
            limite_qtd = st.number_input("Definir limite para 'Pouco Estoque' (menor ou igual a):", min_value=0, value=3, step=1)
        with c_filtro2:
            modo_view = st.selectbox("Filtrar Exibição:", [
                "🔥 Peças Críticas COM Pouco Estoque (Prioridade Máxima)",
                "⚠️ Apenas Peças com Pouco Estoque",
                "🚨 Apenas Peças Marcadas como Críticas (Qualquer quantidade)",
                "📋 Todas as Peças (Ordenadas por menor quantidade)"
            ])

        if "Prioridade Máxima" in modo_view:
            df_resultado = df_bc[(df_bc['critico'] == True) & (df_bc['quanti'] <= limite_qtd)]
        elif "Pouco Estoque" in modo_view:
            df_resultado = df_bc[df_bc['quanti'] <= limite_qtd]
        elif "Marcadas como Críticas" in modo_view:
            df_resultado = df_bc[df_bc['critico'] == True]
        else:
            df_resultado = df_bc

        st.metric("Total de Peças Encontradas na Consulta", len(df_resultado))
        
        # --- BOTAO DE DOWNLOAD PARA COMPRAS ---
        if not df_resultado.empty:
            c_btn1, c_btn2 = st.columns(2)
            
            # Gerar arquivo PDF
            pdf_bytes = gerar_pdf_compras(df_resultado)
            with c_btn1:
                st.download_button(
                    label="📄 Baixar Documento de Compras (PDF)",
                    data=pdf_bytes,
                    file_name=f"solicitacao_compras_{datetime.now().strftime('%d_%m_%Y')}.pdf",
                    mime="application/pdf"
                )

            # Gerar arquivo Excel/CSV
            csv_data = df_resultado.to_csv(index=False).encode('utf-8-sig')
            with c_btn2:
                st.download_button(
                    label="📊 Baixar Tabela em Excel (CSV)",
                    data=csv_data,
                    file_name=f"lista_compras_{datetime.now().strftime('%d_%m_%Y')}.csv",
                    mime="text/csv"
                )

        st.divider()

        if df_resultado.empty:
            st.success("Nenhuma peça atende aos critérios do filtro selecionado!")
        else:
            st.dataframe(
                df_resultado[['id', 'nome', 'cod', 'cod_ref', 'quanti', 'critico', 'estante', 'prateleira', 'caixa', 'ncm']],
                use_container_width=True,
                hide_index=True
            )

# =========================================================
# MÓDULO 6: CADASTRO E EDIÇÃO DE PEÇAS
# =========================================================
elif menu == "➕ Cadastrar / Editar Peças":
    st.title("➕ Gestão de Peças e Materiais")
    
    tab_cad, tab_especial, tab_edit = st.tabs([
        "Cadastrar Novo Material", 
        "⭐ Cadastrar Peça Especial", 
        "Editar / Excluir Existente"
    ])
    
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
            
            is_critico = st.checkbox("⚠️ Item Crítico (Prioridade Alta / Alerta de Reposição)")

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
                            INSERT INTO estoque (nome, cod, cod_ref, ncm, estante, prateleira, caixa, quanti, preco, critico)
                            VALUES (:nome, :cod, :ref, :ncm, :estante, :prateleira, :caixa, :quanti, :preco, :critico)
                        """), {
                            "nome": nome, "cod": cod, "ref": ref, "ncm": ncm.strip(),
                            "estante": estante, "prateleira": prateleira, "caixa": caixa,
                            "quanti": qtd, "preco": preco, "critico": is_critico
                        })
                    registrar_historico("CADASTRO", nome, qtd, f"Crítico: {'Sim' if is_critico else 'Não'}")
                    st.success(f"Material '{nome}' cadastrado no Supabase!")

    # SUB-ABA 2: CADASTRO DE PEÇA ESPECIAL
    with tab_especial:
        st.subheader("⭐ Cadastrar Peça Especial / Usinada / Sob Encomenda")
        with st.form("form_cadastro_especial", clear_on_submit=True):
            nome_esp = st.text_input("Nome da Peça Especial / Projeto *")
            
            ce1, ce2 = st.columns(2)
            with ce1:
                cod_esp = st.text_input("Código Interno Especial:")
                ref_esp = st.text_input("Código Desenho / Referência:")
                ncm_esp = st.text_input("NCM (Formato XXXX.XX.XX) *", placeholder="Ex: 8481.80.99")
                preco_esp = st.number_input("Preço Estimado / Custo (R$):", min_value=0.0, step=0.01)
            with ce2:
                estante_esp = st.text_input("Estante:")
                prateleira_esp = st.text_input("Prateleira:")
                caixa_esp = st.text_input("Caixa / Posição:")
                qtd_esp = st.number_input("Quantidade Inicial:", min_value=0, step=1)
            
            obs_especial = st.text_area("Observação Técnica / Detalhes do Projeto Especial:")
            is_critico_esp = st.checkbox("⚠️ Marcar como Item Crítico Especial", value=True)

            btn_salvar_especial = st.form_submit_button("⭐ CADASTRAR PEÇA ESPECIAL")

            if btn_salvar_especial:
                if not nome_esp:
                    st.warning("O campo Nome da Peça Especial é obrigatório!")
                elif not ncm_esp:
                    st.error("O campo NCM é obrigatório!")
                elif not validar_ncm(ncm_esp):
                    st.error("Formato do NCM inválido! Utilize XXXX.XX.XX")
                else:
                    nome_final = f"[ESPECIAL] {nome_esp}"
                    engine = obter_engine()
                    with engine.begin() as conn:
                        conn.execute(text("""
                            INSERT INTO estoque (nome, cod, cod_ref, ncm, estante, prateleira, caixa, quanti, preco, critico)
                            VALUES (:nome, :cod, :ref, :ncm, :estante, :prateleira, :caixa, :quanti, :preco, :critico)
                        """), {
                            "nome": nome_final, "cod": cod_esp, "ref": ref_esp, "ncm": ncm_esp.strip(),
                            "estante": estante_esp, "prateleira": prateleira_esp, "caixa": caixa_esp,
                            "quanti": qtd_esp, "preco": preco_esp, "critico": is_critico_esp
                        })
                    obs_log = f"Peça Especial | Obs: {obs_especial}" if obs_especial else "Peça Especial"
                    registrar_historico("CADASTRO_ESPECIAL", nome_final, qtd_esp, obs_log)
                    st.success(f"Peça Especial '{nome_final}' cadastrada com sucesso!")

    # SUB-ABA 3: EDIÇÃO INDIVIDUAL POR ID E FILTRO
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

                    val_critico = bool(row_e['critico']) if 'critico' in row_e and pd.notna(row_e['critico']) else False
                    ecritico = st.checkbox("⚠ Item Crítico (Prioridade Alta / Alerta de Reposição)", value=val_critico)

                    b_edit = st.form_submit_button("💾 Salvar Alterações Apenas Nesta Peça")
                    if b_edit:
                        if not validar_ncm(encm):
                            st.error("Formato NCM inválido! Use XXXX.XX.XX")
                        else:
                            with engine.begin() as conn:
                                conn.execute(text("""
                                    UPDATE estoque 
                                    SET nome=:nome, cod=:cod, cod_ref=:ref, ncm=:ncm, estante=:est, prateleira=:prat, caixa=:caixa, quanti=:qtd, preco=:preco, critico=:critico
                                    WHERE id=:id
                                """), {
                                    "nome": enome, "cod": ecod, "ref": eref, "ncm": encm,
                                    "est": eestante, "prat": eprat, "caixa": ecaixa,
                                    "qtd": eqtd, "preco": epreco, "critico": ecritico, "id": id_material
                                })
                            registrar_historico("EDICAO", enome, eqtd, f"ID #{id_material} modificado. Crítico: {'Sim' if ecritico else 'Não'}")
                            st.success("Peça atualizada no banco em nuvem!")
                            st.rerun()

# =========================================================
# MÓDULO 7: HISTÓRICO (LOGS)
# =========================================================
elif menu == "📜 Histórico (Logs)":
    st.title("📜 Histórico de Movimentações e Logs")
    engine = obter_engine()
    df_hist = pd.read_sql("SELECT * FROM historico ORDER BY id DESC", engine)

    if df_hist.empty:
        st.info("Nenhuma movimentação registrada no histórico.")
    else:
        st.dataframe(df_hist, use_container_width=True)
