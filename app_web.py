import os
import re
import sqlite3
import glob
import urllib.parse
import requests
from datetime import datetime
import pandas as pd
import plotly.express as px
import streamlit as st

# =========================================================
# 1. CONFIGURAÇÃO DA PÁGINA E DIRETÓRIOS (CAMINHOS ABSOLUTOS)
# =========================================================
st.set_page_config(
    page_title="Estoque Requipel",
    page_icon="📦",
    layout="wide"
)

DIRETORIO_BASE = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_BANCO = os.path.join(DIRETORIO_BASE, "banco_almoxarifado.db")
PASTA_UPLOADS = os.path.join(DIRETORIO_BASE, "uploads_conserto")

if not os.path.exists(PASTA_UPLOADS):
    os.makedirs(PASTA_UPLOADS)

def conectar_banco():
    return sqlite3.connect(ARQUIVO_BANCO)

def validar_ncm(ncm):
    if not ncm:
        return False
    padrao = r"^\d{4}\.\d{2}\.\d{2}$"
    return re.match(padrao, ncm.strip()) is not None

def registrar_historico(tipo, item_nome, quantidade, obs=""):
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO historico (data_hora, tipo, item_nome, quantidade, observacao, usuario)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            tipo,
            item_nome,
            quantidade,
            obs,
            st.session_state.get('usuario_logado', 'Sistema')
        ))
        conn.commit()
        conn.close()
    except Exception:
        pass

# =========================================================
# FUNÇÕES DE ROTA E CÁLCULO DE COMBUSTÍVEL (MELHORADAS)
# =========================================================
def obter_coordenadas(endereco):
    try:
        txt_limpo = endereco.strip()
        url = f"https://nominatim.openstreetmap.org/search?format=json&q={urllib.parse.quote(txt_limpo)}&limit=1"
        headers = {"User-Agent": "RequipelEstoqueApp/2.0 (contato@requipel.com.br)"}
        response = requests.get(url, headers=headers, timeout=6)
        data = response.json()
        
        if data:
            return float(data[0]['lat']), float(data[0]['lon'])
        
        # Fallback: busca por rua e cidade
        partes = txt_limpo.split(',')
        if len(partes) > 1:
            busca_simplificada = f"{partes[0]}, Gravataí, RS"
            url2 = f"https://nominatim.openstreetmap.org/search?format=json&q={urllib.parse.quote(busca_simplificada)}&limit=1"
            res2 = requests.get(url2, headers=headers, timeout=6).json()
            if res2:
                return float(res2[0]['lat']), float(res2[0]['lon'])
    except Exception:
        pass
    return None, None

def calcular_distancia_osrm(lat1, lon1, lat2, lon2):
    try:
        url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("routes"):
            distancia_metros = data["routes"][0]["distance"]
            return distancia_metros / 1000.0
    except Exception:
        pass
    return None

# =========================================================
# FUNÇÃO RESGATADORA INTELIGENTE DE IMAGENS
# =========================================================
def resolver_imagem(caminho_db):
    if not caminho_db or str(caminho_db).strip() == "":
        return None
    
    if os.path.exists(caminho_db):
        return caminho_db
    
    nome_arquivo = os.path.basename(caminho_db).strip()
    caminho_direto = os.path.join(PASTA_UPLOADS, nome_arquivo)
    if os.path.exists(caminho_direto):
        return caminho_direto
    
    if os.path.exists(PASTA_UPLOADS):
        arquivos_pasta = os.listdir(PASTA_UPLOADS)
        for f in arquivos_pasta:
            if nome_arquivo.lower() in f.lower() or f.lower() in nome_arquivo.lower():
                return os.path.join(PASTA_UPLOADS, f)
            
            partes_orig = nome_arquivo.split('_')
            if len(partes_orig) >= 3:
                chave = f"{partes_orig[0]}_{partes_orig[1]}_{partes_orig[2]}"
                if chave.lower() in f.lower():
                    return os.path.join(PASTA_UPLOADS, f)

    return None

def excluir_conserto(id_conserto):
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT item_nome, caminho_foto_peca, caminho_foto_nf FROM consertos WHERE id = ?", (id_conserto,))
    res = cursor.fetchone()
    
    if res:
        nome_item, foto_p, foto_nf = res[0], res[1], res[2]
        
        img_p = resolver_imagem(foto_p)
        if img_p and os.path.exists(img_p):
            try: os.remove(img_p)
            except: pass
            
        img_n = resolver_imagem(foto_nf)
        if img_n and os.path.exists(img_n):
            try: os.remove(img_n)
            except: pass

        cursor.execute("DELETE FROM consertos WHERE id = ?", (id_conserto,))
        conn.commit()
        conn.close()
        
        registrar_historico("EXCLUSAO_CONSERTO", nome_item, 1, "Registro excluído manualmente")
        return True
    conn.close()
    return False

# =========================================================
# 2. INICIALIZAÇÃO DO BANCO
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
            status TEXT DEFAULT 'Aguardando Coleta'
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
    
    try: cursor.execute("ALTER TABLE historico ADD COLUMN observacao TEXT")
    except Exception: pass
        
    try: cursor.execute("ALTER TABLE historico ADD COLUMN usuario TEXT DEFAULT 'Sistema'")
    except Exception: pass
    
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM consertos")
    total_consertos = cursor.fetchone()[0]
    
    if total_consertos == 0 and os.path.exists(PASTA_UPLOADS):
        arquivos = os.listdir(PASTA_UPLOADS)
        pecas = [f for f in arquivos if f.startswith('peca_')]
        
        for p in pecas:
            caminho_p = os.path.join(PASTA_UPLOADS, p)
            timestamp = p.replace('peca_', '').split('_WhatsApp')[0]
            nf_correspondente = ""
            for f in arquivos:
                if f.startswith('nf_') and timestamp in f:
                    nf_correspondente = os.path.join(PASTA_UPLOADS, f)
                    break
            
            cursor.execute("""
                INSERT INTO consertos (item_nome, cod_ref, data_envio, oficina, num_nf, defeito, caminho_foto_peca, caminho_foto_nf, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Em Conserto')
            """, (
                f"Peça Recarregada ({p[:20]})",
                "REF-AUTO",
                datetime.now().strftime("%d/%m/%Y"),
                "Oficina Cadastrada",
                "N/A",
                "Item resgatado automaticamente dos arquivos do GitHub.",
                caminho_p,
                nf_correspondente,
            ))
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
            codigo = st.text_input("Código Master:", type="password")
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

if st.sidebar.button("🚪 Sair / Logout"):
    st.session_state["autenticado"] = False
    st.rerun()

st.sidebar.divider()

menu = st.sidebar.radio(
    "Navegação do Sistema:",
    [
        "📊 Visão Geral / Dashboard",
        "🚚 Calculadora de Frete / Rota",
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
    
    conn = conectar_banco()
    df_est = pd.read_sql_query("SELECT * FROM estoque", conn)
    df_cons = pd.read_sql_query("SELECT * FROM consertos WHERE status IS NULL OR status != 'Retornado'", conn)
    conn.close()

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
# MÓDULO: CALCULADORA DE FRETE / ROTA E COMBUSTÍVEL
# =========================================================
elif menu == "🚚 Calculadora de Frete / Rota":
    st.title("🚚 Calculadora de Rota, Frete e Combustível")
    st.caption("Calcule os custos de deslocamento da entrega com base no veículo, distância e itens do estoque.")

    if "distancia_km_gps" not in st.session_state:
        st.session_state["distancia_km_gps"] = 0.0

    c_esq, c_dir = st.columns([1.2, 1])

    with c_esq:
        st.subheader("1. Configurações do Percurso")
        origem = st.text_input("Endereço da Empresa (Origem):", value="Rod. RS-118, 5245, Gravataí - RS")
        destino = st.text_input("Endereço de Entrega (Destino):", value="Rua Sarandi, 120, Parque Ipiranga, Gravataí - RS")
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            tipo_percurso = st.radio("Percurso:", ["Somente Ida", "Ida e Volta"], index=1)
        with col_m2:
            calc_modo = st.radio("Modo de Distância:", ["Busca Automática (GPS)", "Informar km Manualmente"], index=0)

        if calc_modo == "Busca Automática (GPS)":
            if st.button("📍 Calcular Rota pelo Mapa"):
                if not destino:
                    st.warning("Informe o endereço de destino!")
                else:
                    with st.spinner("Buscando coordenadas no mapa..."):
                        lat1, lon1 = obter_coordenadas(origem)
                        lat2, lon2 = obter_coordenadas(destino)
                        
                        if lat1 and lat2:
                            km = calcular_distancia_osrm(lat1, lon1, lat2, lon2)
                            if km:
                                st.session_state["distancia_km_gps"] = km
                                st.success(f"Rota calculada com sucesso: {km:.2f} km (Só Ida)")
                            else:
                                st.error("Não foi possível traçar o trajeto entre os pontos.")
                        else:
                            st.error("Endereço não localizado pelo GPS. Verifique a grafia ou mude para 'Informar km Manualmente'.")

            distancia_final_km = st.session_state["distancia_km_gps"]
            if distancia_final_km > 0:
                st.info(f"Distância identificada pelo GPS (Só Ida): **{distancia_final_km:.2f} km**")
        else:
            distancia_final_km = st.number_input("Distância em km (Só Ida):", min_value=0.0, value=6.0, step=0.5)

        distancia_total_rodada = distancia_final_km * 2 if tipo_percurso == "Ida e Volta" else distancia_final_km

        st.subheader("2. Dados do Veículo e Combustível")
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            veiculo_nome = st.selectbox("Veículo / Modelo:", ["Furgão / Utilitário", "Carro de Passeio", "Caminhão Pequeno", "Outro"])
        with col_v2:
            consumo_kml = st.number_input("Consumo (km/L):", min_value=1.0, value=10.0, step=0.5)
        with col_v3:
            preco_litro = st.number_input("Gasolina (R$/L):", min_value=1.0, value=5.89, step=0.05)

        st.subheader("3. Adicionais e Peça do Estoque")
        taxa_extra_km = st.number_input("Taxa de Desgaste / Operação por km (R$):", min_value=0.0, value=0.50, step=0.10)
        
        conn = conectar_banco()
        df_pecas_frete = pd.read_sql_query("SELECT id, nome, preco FROM estoque WHERE quanti > 0 ORDER BY nome ASC", conn)
        conn.close()

        valor_peca_selecionada = 0.0
        nome_peca_selecionada = "Nenhuma"

        if not df_pecas_frete.empty:
            dict_pecas = {"[Nenhuma peça vinculada]": (0.0, "Nenhuma")}
            for _, r in df_pecas_frete.iterrows():
                dict_pecas[f"{r['nome']} - R$ {r['preco']:.2f}"] = (r['preco'], r['nome'])
            
            sel_p = st.selectbox("Vincular Peça do Estoque ao Frete:", list(dict_pecas.keys()))
            valor_peca_selecionada, nome_peca_selecionada = dict_pecas[sel_p]

    with c_dir:
        st.subheader("📊 Resumo do Orçamento de Entrega")

        if distancia_total_rodada > 0 and consumo_kml > 0:
            litros_necessarios = distancia_total_rodada / consumo_kml
            custo_combustivel = litros_necessarios * preco_litro
            custo_operacional = distancia_total_rodada * taxa_extra_km
            custo_total_entrega = custo_combustivel + custo_operacional
            valor_total_geral = custo_total_entrega + valor_peca_selecionada

            st.metric("Distância Total Considerada", f"{distancia_total_rodada:.2f} km")
            st.metric("Litros de Combustível", f"{litros_necessarios:.2f} L")
            st.metric("Custo Somente Gasolina", f"R$ {custo_combustivel:.2f}")
            st.metric("Custo Total de Frete (com taxas)", f"R$ {custo_total_entrega:.2f}")

            if valor_peca_selecionada > 0:
                st.metric("Valor da Peça", f"R$ {valor_peca_selecionada:.2f}")
                st.divider()
                st.markdown(f"### 💰 **Total do Orçamento:** R$ {valor_total_geral:.2f}")

            texto_orcamento = f"""*ORÇAMENTO DE ENTREGA - REQUIPEL*
----------------------------------------
📍 *Origem:* {origem}
🏁 *Destino:* {destino}
📏 *Distância Rodada:* {distancia_total_rodada:.1f} km ({tipo_percurso})
🚘 *Veículo:* {veiculo_nome} ({consumo_kml} km/L)

⛽ *Gasto de Combustível:* R$ {custo_combustivel:.2f}
🚚 *Taxa de Entrega / Frete:* R$ {custo_total_entrega:.2f}
📦 *Peça:* {nome_peca_selecionada} (R$ {valor_peca_selecionada:.2f})
----------------------------------------
💰 *TOTAL GERAL:* R$ {valor_total_geral:.2f}
"""
            st.text_area("📋 Texto Formatado para WhatsApp / Cliente:", value=texto_orcamento, height=220)
        else:
            st.info("Clique no botão '📍 Calcular Rota pelo Mapa' para obter a distância real do percurso.")

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
                    p_peca = ""
                    p_nf = ""
                    time_str = datetime.now().strftime('%Y%m%d_%H%M%S')
                    
                    if f_peca:
                        nome_f_peca = f"peca_{time_str}_{f_peca.name.replace(' ', '_')}"
                        p_peca = os.path.join(PASTA_UPLOADS, nome_f_peca)
                        with open(p_peca, "wb") as f:
                            f.write(f_peca.getbuffer())
                    if f_nf:
                        nome_f_nf = f"nf_{time_str}_{f_nf.name.replace(' ', '_')}"
                        p_nf = os.path.join(PASTA_UPLOADS, nome_f_nf)
                        with open(p_nf, "wb") as f:
                            f.write(f_nf.getbuffer())

                    conn = conectar_banco()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO consertos (item_nome, cod_ref, data_envio, oficina, num_nf, defeito, caminho_foto_peca, caminho_foto_nf, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Aguardando Coleta')
                    """, (item_nome, cod_ref, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), oficina, num_nf, defeito, p_peca, p_nf))
                    conn.commit()
                    conn.close()
                    registrar_historico("CADASTRO_CONSERTO", item_nome, 1, f"Oficina: {oficina}")
                    st.success("Peça cadastrada com sucesso! Agora está em 'Aguardando Coleta'.")
                    st.rerun()

    # TAB 2: AGUARDANDO COLETA
    with tab_coleta:
        st.subheader("⏳ Peças Aguardando Coleta para Ir à Oficina")
        conn = conectar_banco()
        df_coleta = pd.read_sql_query("SELECT * FROM consertos WHERE status = 'Aguardando Coleta' OR status = 'Em espera de coleta' ORDER BY id DESC", conn)
        conn.close()

        if df_coleta.empty:
            st.info("Nenhuma peça aguardando coleta no momento.")
        else:
            for idx, row in df_coleta.iterrows():
                col_img, col_detalhes, col_acao = st.columns([1.5, 3, 1.5])
                
                with col_img:
                    col_p, col_nf = st.columns(2)
                    img_peca = resolver_imagem(row['caminho_foto_peca'])
                    with col_p:
                        st.caption("📷 Foto Peça")
                        if img_peca: st.image(img_peca, use_container_width=True)
                        else: st.info("Sem foto")
                    
                    img_nf = resolver_imagem(row['caminho_foto_nf'])
                    with col_nf:
                        st.caption("📄 Foto NF")
                        if img_nf: st.image(img_nf, use_container_width=True)
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
                        conn = conectar_banco()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE consertos SET status = 'Em Conserto' WHERE id = ?", (row['id'],))
                        conn.commit()
                        conn.close()
                        registrar_historico("COLETADO_CONSERTO", row['item_nome'], 1, f"Oficina: {row['oficina']}")
                        st.success("Coleta confirmada! Peça movida para 'Em Manutenção'.")
                        st.rerun()

                    if st.button("🗑️ Excluir Registro", key=f"del_col_{row['id']}", type="secondary"):
                        if excluir_conserto(row['id']):
                            st.success("Registo excluído com sucesso!")
                            st.rerun()

                st.divider()

    # TAB 3: EM MANUTENÇÃO
    with tab_manut:
        st.subheader("🛠️ Peças em Manutenção na Oficina")
        conn = conectar_banco()
        df_manut = pd.read_sql_query("SELECT * FROM consertos WHERE status = 'Em Conserto' OR status IS NULL ORDER BY id DESC", conn)
        conn.close()

        if df_manut.empty:
            st.info("Nenhuma peça atualmente em manutenção na oficina.")
        else:
            for idx, row in df_manut.iterrows():
                col_img, col_detalhes, col_acao = st.columns([1.5, 3, 1.5])
                
                with col_img:
                    col_p, col_nf = st.columns(2)
                    img_peca = resolver_imagem(row['caminho_foto_peca'])
                    with col_p:
                        st.caption("📷 Foto Peça")
                        if img_peca: st.image(img_peca, use_container_width=True)
                        else: st.info("Sem foto")
                    
                    img_nf = resolver_imagem(row['caminho_foto_nf'])
                    with col_nf:
                        st.caption("📄 Foto NF")
                        if img_nf: st.image(img_nf, use_container_width=True)
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
                        conn = conectar_banco()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE consertos SET status = 'Retornado' WHERE id = ?", (row['id'],))
                        conn.commit()
                        conn.close()
                        registrar_historico("RETORNO_CONSERTO", row['item_nome'], 1, f"Oficina: {row['oficina']}")
                        st.success("Retorno registrado com sucesso!")
                        st.rerun()

                    if st.button("🗑️ Excluir Registro", key=f"del_man_{row['id']}", type="secondary"):
                        if excluir_conserto(row['id']):
                            st.success("Registo excluído com sucesso!")
                            st.rerun()

                st.divider()

    # TAB 4: PEÇAS RETORNADAS
    with tab_ret:
        st.subheader("✅ Histórico de Peças Retornadas da Manutenção")
        conn = conectar_banco()
        df_ret = pd.read_sql_query("SELECT * FROM consertos WHERE status = 'Retornado' ORDER BY id DESC", conn)
        conn.close()

        if df_ret.empty:
            st.info("Nenhum histórico de retorno de peças registrado ainda.")
        else:
            st.dataframe(df_ret, use_container_width=True)

# =========================================================
# MÓDULO 3: MOVIMENTAÇÃO DE ESTOQUE
# =========================================================
elif menu == "📦 Movimentação de Estoque":
    st.title("📦 Movimentação de Entrada e Saída de Materiais")
    
    conn = conectar_banco()
    df_estoque = pd.read_sql_query("SELECT id, nome, cod, cod_ref, quanti FROM estoque ORDER BY nome ASC", conn)
    conn.close()

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
                conn = conectar_banco()
                cursor = conn.cursor()
                
                cursor.execute("SELECT nome, quanti FROM estoque WHERE id = ?", (mat_id,))
                res_mat = cursor.fetchone()
                if res_mat:
                    nome_mat, qtd_atual = res_mat[0], res_mat[1]

                    if "SAÍDA" in tipo_mov and qtd_mov > qtd_atual:
                        st.error("Quantidade de saída é maior do que o estoque disponível!")
                        conn.close()
                    else:
                        nova_qtd = (qtd_atual + qtd_mov) if "ENTRADA" in tipo_mov else (qtd_atual - qtd_mov)
                        cursor.execute("UPDATE estoque SET quanti = ? WHERE id = ?", (nova_qtd, mat_id))
                        conn.commit()
                        conn.close()
                        
                        tipo_str = "ENTRADA" if "ENTRADA" in tipo_mov else "SAÍDA"
                        registrar_historico(tipo_str, nome_mat, qtd_mov, obs_mov)
                        
                        st.success(f"Movimentação realizada! Novo estoque de '{nome_mat}': {nova_qtd}")
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

    # SUB-ABA 2: EDIÇÃO INDIVIDUAL POR ID E FILTRO
    with tab_edit:
        conn = conectar_banco()
        df_edit = pd.read_sql_query("SELECT * FROM estoque ORDER BY nome ASC", conn)
        conn.close()

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
                            conn = conectar_banco()
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE estoque 
                                SET nome=?, cod=?, cod_ref=?, ncm=?, estante=?, prateleira=?, caixa=?, quanti=?, preco=?
                                WHERE id=?
                            """, (enome, ecod, eref, encm, eestante, eprat, ecaixa, eqtd, epreco, id_material))
                            conn.commit()
                            conn.close()
                            registrar_historico("EDICAO", enome, eqtd, f"ID #{id_material} modificado")
                            st.success("Peça atualizada com sucesso!")
                            st.rerun()

# =========================================================
# MÓDULO 5: HISTÓRICO (LOGS)
# =========================================================
elif menu == "📜 Histórico (Logs)":
    st.title("📜 Histórico de Movimentações e Logs")
    conn = conectar_banco()
    df_hist = pd.read_sql_query("SELECT * FROM historico ORDER BY id DESC", conn)
    conn.close()

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
    
    conn = conectar_banco()
    df_ncm = pd.read_sql_query("SELECT DISTINCT ncm, nome, cod_ref FROM estoque ORDER BY ncm ASC", conn)
    conn.close()

    termo_ncm = st.text_input("Digite o número do NCM ou nome da peça:")
    if termo_ncm:
        df_ncm = df_ncm[
            df_ncm['ncm'].astype(str).str.contains(termo_ncm, case=False, na=False) |
            df_ncm['nome'].astype(str).str.contains(termo_ncm, case=False, na=False)
        ]

    st.dataframe(df_ncm, use_container_width=True)
