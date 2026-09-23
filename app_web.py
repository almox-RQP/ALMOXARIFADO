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
    page_title="Estoque Requipel", page_icon="📦", layout="wide"
)

ARQUIVO_BANCO = "banco_almoxarifado.db"
PASTA_UPLOADS = "uploads_conserto"

# Cria a pasta para salvar as fotos das peças e NFs caso não exista
if not os.path.exists(PASTA_UPLOADS):
    os.makedirs(PASTA_UPLOADS)

# =========================================================
# LISTA DE PEÇAS INICIAIS
# =========================================================
ITENS_INICIAIS = [
    ("6384", "", "0000.00.00", "LIXA DE 40", 20),
    ("5401", "", "0000.00.00", "LIXA DE 50", 28),
    ("1802", "", "0000.00.00", "LIXA DE 60", 30),
    ("6385", "", "0000.00.00", "LIXA DE 100", 5),
    ("434", "", "0000.00.00", "LIXA DE 320", 10),
    ("435", "", "0000.00.00", "LIXA DE 400", 56),
    ("1801", "", "0000.00.00", "TINTA SPRAY BRANCA", 10),
    ("1799", "", "0000.00.00", "TINTA SPRAY VERMELHA", 1),
    ("6386", "", "0000.00.00", "ESPUMA EXPANSIVA", 1),
    ("6252", "", "0000.00.00", "DILUIENTE PARA EOXI 900ML", 3),
]


# =========================================================
# FUNÇÕES DE VALIDAÇÃO
# =========================================================
def validar_ncm(ncm_str):
    # Formato esperado: XXXX.XX.XX (4 dígitos, ponto, 2 dígitos, ponto, 2 dígitos)
    padrao = r"^\d{4}\.\d{2}\.\d{2}$"
    return bool(re.match(padrao, ncm_str.strip()))


# =========================================================
# FUNÇÕES DO BANCO DE DADOS
# =========================================================
def conectar_banco():
    return sqlite3.connect(ARQUIVO_BANCO)


def inicializar_banco():
    conn = conectar_banco()
    cursor = conn.cursor()

    # Tabela principal de estoque
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estoque (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cod TEXT,
            cod_ref TEXT,
            ncm TEXT DEFAULT '0000.00.00',
            estante TEXT,
            prateleira TEXT,
            caixa TEXT,
            quanti INTEGER NOT NULL,
            preco REAL DEFAULT 0.0
        )
    """)

    # Adiciona colunas novas caso o banco já existisse em versão anterior
    try:
        cursor.execute(
            "ALTER TABLE estoque ADD COLUMN preco REAL DEFAULT 0.0"
        )
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute(
            "ALTER TABLE estoque ADD COLUMN ncm TEXT DEFAULT '0000.00.00'"
        )
    except sqlite3.OperationalError:
        pass

    # Tabela de Histórico / Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_hora TEXT NOT NULL,
            tipo TEXT NOT NULL,
            item_nome TEXT NOT NULL,
            quantidade INTEGER NOT NULL
        )
    """)

    # Tabela para Controle de Peças em Conserto
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conserto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_peca TEXT NOT NULL,
            cod_peca TEXT,
            oficina TEXT,
            num_nf TEXT,
            defeito TEXT,
            caminho_foto_peca TEXT,
            caminho_foto_nf TEXT,
            data_envio TEXT,
            data_retorno TEXT,
            status TEXT DEFAULT 'Em Conserto',
            obs_retorno TEXT
        )
    """)

    # Tabela para Controle de Licença / Trava de 90 Dias
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_licenca (
            id INTEGER PRIMARY KEY,
            data_liberacao TEXT NOT NULL
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM estoque")
    total_itens = cursor.fetchone()[0]

    if total_itens == 0:
        for cod, cod_ref, ncm, nome, quanti in ITENS_INICIAIS:
            cursor.execute(
                """
                INSERT INTO estoque (nome, cod, cod_ref, ncm, estante, prateleira, caixa, quanti, preco)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (nome, cod, cod_ref, ncm, "", "", "", quanti, 0.0),
            )

    conn.commit()
    conn.close()


def obter_ultima_liberacao():
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT data_liberacao FROM controle_licenca WHERE id = 1"
    )
    res = cursor.fetchone()

    if not res:
        hoje_str = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            "INSERT INTO controle_licenca (id, data_liberacao) VALUES (1, ?)",
            (hoje_str,),
        )
        conn.commit()
        conn.close()
        return datetime.now()

    conn.close()
    return datetime.strptime(res[0], "%Y-%m-%d")


def atualizar_data_liberacao():
    conn = conectar_banco()
    cursor = conn.cursor()
    hoje_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        "UPDATE controle_licenca SET data_liberacao = ? WHERE id = 1",
        (hoje_str,),
    )
    conn.commit()
    conn.close()


def registrar_historico(tipo, item_nome, quantidade):
    conn = conectar_banco()
    cursor = conn.cursor()
    data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO historico (data_hora, tipo, item_nome, quantidade)
        VALUES (?, ?, ?, ?)
    """,
        (data_hora, tipo, item_nome, quantidade),
    )
    conn.commit()
    conn.close()


def obter_lista_itens():
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT nome FROM estoque")
    itens = [row[0] for row in cursor.fetchall()]
    conn.close()
    return itens


def excluir_item_banco(item_id, nome_item):
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM estoque WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    registrar_historico("EXCLUSÃO", nome_item, 0)


def salvar_arquivo_upload(uploaded_file, prefixo):
    if uploaded_file is not None:
        nome_arquivo = (
            f"{prefixo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}"
        )
        caminho_completo = os.path.join(PASTA_UPLOADS, nome_arquivo)
        with open(caminho_completo, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return caminho_completo
    return None


inicializar_banco()

# =========================================================
# CONTROLE DE SESSÃO, LICENÇA E LOGIN
# =========================================================
if "logado" not in st.session_state:
    st.session_state["logado"] = False

data_ultima = obter_ultima_liberacao()
dias_decorridos = (datetime.now() - data_ultima).days
licenca_bloqueada = dias_decorridos >= 90

if not st.session_state["logado"]:
    st.title("🔐 Acesso ao Sistema - Estoque Requipel")
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        if licenca_bloqueada:
            st.error("⚠️ LICENÇA EXPIRADA OU MANUTENÇÃO REQUERIDA!")
            st.warning(
                "O acesso ao sistema foi suspenso temporariamente. Insira a chave de autorização master para liberar."
            )

            with st.form("form_master"):
                chave_master = st.text_input(
                    "Código de Autorização Master", type="password"
                )
                btn_master = st.form_submit_button("RENOVAR E LIBERAR SISTEMA")

                if btn_master:
                    if chave_master == "202739":
                        atualizar_data_liberacao()
                        st.success(
                            "Sistema renovado com sucesso por mais 90 dias!"
                        )
                        st.rerun()
                    else:
                        st.error("Código de autorização incorreto!")

        else:
            with st.form("form_login"):
                usuario = st.text_input("Usuário")
                senha = st.text_input("Senha", type="password")
                btn_login = st.form_submit_button("ENTRAR")

                if btn_login:
                    if usuario == "admin" and senha == "1234":
                        st.session_state["logado"] = True
                        st.success("Login efetuado com sucesso!")
                        st.rerun()
                    elif senha == "202739":
                        st.session_state["logado"] = True
                        atualizar_data_liberacao()
                        st.rerun()
                    else:
                        st.error("Usuário ou senha incorretos!")
    st.stop()

# =========================================================
# MENU LATERAL (SIDEBAR)
# =========================================================
st.sidebar.title("📦 ESTOQUE")
opcao = st.sidebar.radio(
    "Navegação",
    [
        "🔍 Buscar e Retirar",
        "📊 Visualizar / Gerenciar Estoque",
        "🛠️ Peças em Conserto",
        "✏️ Editar Item",
        "💰 Valores do Estoque",
        "📥 Entradas (Reposição)",
        "➕ Cadastrar Item",
        "📜 Histórico (Logs)",
    ],
)

if st.sidebar.button("Sair / Logout"):
    st.session_state["logado"] = False
    st.rerun()

# =========================================================
# 1. BUSCAR E RETIRAR
# =========================================================
if opcao == "🔍 Buscar e Retirar":
    st.title("🔍 Consulta e Saída de Materiais")
    termo = st.text_input("Digite o Nome, Código, Cód. REF ou NCM:")

    if termo:
        conn = conectar_banco()
        cursor = conn.cursor()

        query = """
            SELECT id, nome, cod, cod_ref, ncm, estante, prateleira, caixa, quanti, preco 
            FROM estoque 
            WHERE LOWER(nome) LIKE ? OR LOWER(cod) = ? OR LOWER(cod_ref) = ? OR LOWER(ncm) = ?
        """
        termo_like = f"%{termo.lower()}%"
        cursor.execute(
            query,
            (termo_like, termo.lower(), termo.lower(), termo.lower()),
        )
        resultados = cursor.fetchall()
        conn.close()

        if resultados:
            if len(resultados) > 1:
                st.info(
                    f"Foram encontrados {len(resultados)} materiais correspondentes:"
                )
                dict_resultados = {
                    f"{r[1]} (Cód: {r[2] if r[2] else 'S/C'} | REF: {r[3] if r[3] else 'S/REF'} | NCM: {r[4] if r[4] else 'S/NCM'})": r
                    for r in resultados
                }
                item_selecionado_label = st.selectbox(
                    "Selecione o item desejado na lista abaixo:",
                    options=list(dict_resultados.keys()),
                )
                resultado_final = dict_resultados[item_selecionado_label]
            else:
                resultado_final = resultados[0]

            (
                item_id,
                nome,
                cod,
                cod_ref,
                ncm,
                estante,
                prateleira,
                caixa,
                quanti,
                preco,
            ) = resultado_final

            st.divider()
            st.subheader(f"📍 Item Selecionado: {nome}")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Cód. Interno:** {cod if cod else 'N/A'}")
                st.write(
                    f"**Cód. REF:** {cod_ref if cod_ref else 'N/A'}"
                )
                st.write(f"**NCM:** {ncm if ncm else 'N/A'}")
                st.write(f"**Preço Unitário:** R$ {preco:,.2f}")
            with col2:
                st.write(f"**Estante:** {estante if estante else 'N/A'}")
                st.write(
                    f"**Prateleira:** {prateleira if prateleira else 'N/A'}"
                )
                st.write(f"**Caixa:** {caixa if caixa else 'N/A'}")
            with col3:
                if quanti <= 3:
                    st.error(
                        f"📊 Saldo Disponível: {quanti} un. ⚠️ (ESTOQUE BAIXO!)"
                    )
                else:
                    st.metric(
                        label="📊 Saldo Disponível", value=f"{quanti} un."
                    )

            st.divider()
            with st.form("form_baixa"):
                qtd_saida = st.number_input(
                    "Quantidade a retirar (Baixa):", min_value=1, step=1
                )
                btn_retirar = st.form_submit_button("DAR BAIXA / RETIRAR")

                if btn_retirar:
                    if qtd_saida > quanti:
                        st.error(
                            f"Saldo insuficiente! Você só possui {quanti} unidades em estoque."
                        )
                    else:
                        novo_saldo = quanti - qtd_saida
                        conn_b = conectar_banco()
                        cursor_b = conn_b.cursor()
                        cursor_b.execute(
                            "UPDATE estoque SET quanti = ? WHERE id = ?",
                            (novo_saldo, item_id),
                        )
                        conn_b.commit()
                        conn_b.close()

                        registrar_historico("SAÍDA", nome, qtd_saida)
                        st.success(
                            f"Retirada de {qtd_saida} un. realizada com sucesso!"
                        )
                        st.rerun()
        else:
            st.warning("Nenhum material foi localizado com esses termos!")

# =========================================================
# 2. VISUALIZAR E GERENCIAR ESTOQUE
# =========================================================
elif opcao == "📊 Visualizar / Gerenciar Estoque":
    st.title("📊 Tabela Geral de Estoque")

    conn = conectar_banco()
    df = pd.read_sql_query(
        "SELECT id AS ID, nome AS Nome, cod AS 'Cód. Interno', cod_ref AS 'Cód. REF', ncm AS 'NCM', estante AS Estante, prateleira AS Prateleira, caixa AS Caixa, quanti AS Qtd, preco AS 'Preço Unit. (R$)' FROM estoque",
        conn,
    )
    conn.close()

    total_tipos_itens = len(df)
    total_unidades = df["Qtd"].sum() if not df.empty else 0

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric(
            label="📦 Tipos de Peças Cadastradas",
            value=f"{total_tipos_itens} itens",
        )
    with col_m2:
        st.metric(
            label="📊 Total de Unidades no Estoque", value=f"{total_unidades} un."
        )

    st.divider()
    st.dataframe(df, use_container_width=True)

    st.divider()
    st.subheader("🗑️ Apagar Item do Estoque")

    col_sel, col_btn = st.columns([3, 1])

    with col_sel:
        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, cod, cod_ref, ncm FROM estoque")
        itens_para_apagar = cursor.fetchall()
        conn.close()

        opcoes_apagar = {
            f"Cód: {item[2] if item[2] else 'S/C'} | REF: {item[3] if item[3] else 'S/REF'} | NCM: {item[4] if item[4] else 'S/NCM'} - {item[1]} (ID {item[0]})": (
                item[0],
                item[1],
            )
            for item in itens_para_apagar
        }

        if opcoes_apagar:
            item_escolhido = st.selectbox(
                "Selecione o item que deseja apagar (pesquise por nome ou código):",
                options=list(opcoes_apagar.keys()),
            )

    with col_btn:
        st.write("")
        st.write("")
        if opcoes_apagar and st.button("❌ APAGAR ITEM", type="primary"):
            id_excluir, nome_excluir = opcoes_apagar[item_escolhido]
            excluir_item_banco(id_excluir, nome_excluir)
            st.success(f"Item '{nome_excluir}' apagado com sucesso!")
            st.rerun()

# =========================================================
# 3. PEÇAS EM CONSERTO
# =========================================================
elif opcao == "🛠️ Peças em Conserto":
    st.title("🛠️ Controle de Peças em Conserto / Manutenção")

    aba_ativos, aba_novo, aba_historico = st.tabs(
        [
            "🔴 Em Conserto (Ativos)",
            "➕ Enviar Peça para Conserto",
            "✅ Histórico de Retornos",
        ]
    )

    with aba_ativos:
        st.subheader("📋 Peças Aguardando Retorno da Manutenção")

        conn = conectar_banco()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nome_peca, cod_peca, oficina, num_nf, defeito, caminho_foto_peca, caminho_foto_nf, data_envio 
            FROM conserto 
            WHERE status = 'Em Conserto'
            ORDER BY id DESC
        """
        )
        itens_conserto = cursor.fetchall()
        conn.close()

        if itens_conserto:
            for item in itens_conserto:
                (
                    c_id,
                    c_nome,
                    c_cod,
                    c_oficina,
                    c_nf,
                    c_defeito,
                    c_foto_peca,
                    c_foto_nf,
                    c_data_envio,
                ) = item

                with st.container():
                    col_img_p, col_img_nf, col_info, col_acao = st.columns(
                        [1.5, 1.5, 3, 2]
                    )

                    with col_img_p:
                        st.caption("📷 Foto da Peça")
                        if c_foto_peca and os.path.exists(c_foto_peca):
                            st.image(c_foto_peca, use_container_width=True)
                        else:
                            st.info("Sem foto cadastrada")

                    with col_img_nf:
                        st.caption("📄 Foto da NF")
                        if c_foto_nf and os.path.exists(c_foto_nf):
                            st.image(c_foto_nf, use_container_width=True)
                        else:
                            st.info("Sem foto da NF")

                    with col_info:
                        st.markdown(f"### **{c_nome}**")
                        st.write(f"**Cód. Interno/REF:** {c_cod if c_cod else 'N/A'}")
                        st.write(f"**Data de Envio:** {c_data_envio}")
                        st.write(f"**Oficina / Empresa:** {c_oficina if c_oficina else 'N/A'}")
                        st.write(f"**Nº da NF de Remessa:** {c_nf if c_nf else 'N/A'}")
                        st.write(f"**Defeito:** {c_defeito if c_defeito else 'Não informado'}")

                    with col_acao:
                        st.write("### ")
                        st.warning("⏳ Status: Em Conserto")

                        with st.popover("✅ Registrar Retorno"):
                            st.write("Confirmar retorno desta peça ao estoque?")
                            obs_r = st.text_area(
                                "Observações do Reparo (opcional):",
                                key=f"obs_{c_id}",
                            )
                            if st.button(
                                "Confirmar Retorno",
                                type="primary",
                                key=f"btn_ret_{c_id}",
                            ):
                                data_hoje = datetime.now().strftime(
                                    "%d/%m/%Y %H:%M:%S"
                                )
                                conn_u = conectar_banco()
                                cursor_u = conn_u.cursor()
                                cursor_u.execute(
                                    """
                                    UPDATE conserto 
                                    SET status = 'Concluído', data_retorno = ?, obs_retorno = ? 
                                    WHERE id = ?
                                """,
                                    (data_hoje, obs_r, c_id),
                                )
                                conn_u.commit()
                                conn_u.close()

                                registrar_historico(
                                    "RETORNO CONSERTO", c_nome, 1
                                )
                                st.success("Peça marcada como concluída e enviada ao histórico!")
                                st.rerun()

                st.divider()
        else:
            st.info("Nenhuma peça atualmente em conserto.")

    with aba_novo:
        st.subheader("📝 Registrar Envio de Peça para Reparo")

        with st.form("form_novo_conserto", clear_on_submit=True):
            col_f1, col_f2 = st.columns(2)

            with col_f1:
                p_nome = st.text_input("Nome da Peça / Equipamento (Obrigatório):")
                p_cod = st.text_input("Código Interno / REF (Opcional):")
                p_oficina = st.text_input("Empresa / Oficina que fará o conserto:")
                p_nf = st.text_input("Número da NF de Remessa:")

            with col_f2:
                p_defeito = st.text_area("Descrição do Defeito / Motivo do Envio:")
                file_peca = st.file_uploader(
                    "📷 Anexar Foto da Peça:", type=["png", "jpg", "jpeg"]
                )
                file_nf = st.file_uploader(
                    "📄 Anexar Foto da Nota Fiscal:", type=["png", "jpg", "jpeg"]
                )

            btn_salvar_conserto = st.form_submit_button(
                "🚀 REGISTRAR ENVIO PARA CONSERTO", type="primary"
            )

            if btn_salvar_conserto:
                if not p_nome:
                    st.warning("O campo Nome da Peça é obrigatório!")
                else:
                    path_peca = salvar_arquivo_upload(file_peca, "peca")
                    path_nf = salvar_arquivo_upload(file_nf, "nf")
                    data_envio = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                    conn = conectar_banco()
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO conserto 
                        (nome_peca, cod_peca, oficina, num_nf, defeito, caminho_foto_peca, caminho_foto_nf, data_envio, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Em Conserto')
                    """,
                        (
                            p_nome,
                            p_cod,
                            p_oficina,
                            p_nf,
                            p_defeito,
                            path_peca,
                            path_nf,
                            data_envio,
                        ),
                    )
                    conn.commit()
                    conn.close()

                    registrar_historico("ENVIO CONSERTO", p_nome, 1)
                    st.success(f"Registro de envio da peça '{p_nome}' salvo com sucesso!")
                    st.rerun()

    with aba_historico:
        st.subheader("📜 Histórico de Manutenções Concluídas")

        conn = conectar_banco()
        df_conserto = pd.read_sql_query(
            """
            SELECT 
                nome_peca AS 'Peça', 
                cod_peca AS 'Cód.', 
                oficina AS 'Oficina / Empresa', 
                num_nf AS 'Nº NF', 
                data_envio AS 'Data Envio', 
                data_retorno AS 'Data Retorno', 
                obs_retorno AS 'Observações do Reparo'
            FROM conserto 
            WHERE status = 'Concluído'
            ORDER BY id DESC
        """,
            conn,
        )
        conn.close()

        if not df_conserto.empty:
            st.dataframe(df_conserto, use_container_width=True)
        else:
            st.info("Nenhum histórico de manutenção concluída ainda.")

# =========================================================
# 4. EDITAR ITEM
# =========================================================
elif opcao == "✏️ Editar Item":
    st.title("✏️ Editar Informações, NCM e Preço do Item")

    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nome, cod, cod_ref, ncm, estante, prateleira, caixa, quanti, preco FROM estoque"
    )
    todos_itens = cursor.fetchall()
    conn.close()

    if todos_itens:
        opcoes = {}
        for item in todos_itens:
            cod_txt = f"Cód: {item[2]}" if item[2] else ""
            ref_txt = f"REF: {item[3]}" if item[3] else ""
            ncm_txt = f"NCM: {item[4]}" if item[4] else ""
            codigos = " | ".join(filter(None, [cod_txt, ref_txt, ncm_txt]))
            prefixo = f"[{codigos}] " if codigos else ""

            label = f"{prefixo}{item[1]} (ID: {item[0]})"
            opcoes[label] = item

        selecionado = st.selectbox(
            "Digite o Código, REF, NCM ou Nome do item para editar:",
            options=list(opcoes.keys()),
        )
        dados = opcoes[selecionado]

        with st.form("form_editar"):
            nov_nome = st.text_input("Nome do Material", value=dados[1])
            nov_cod = st.text_input(
                "Código Interno", value=dados[2] if dados[2] else ""
            )
            nov_ref = st.text_input(
                "Cód. REF", value=dados[3] if dados[3] else ""
            )
            nov_ncm = st.text_input(
                "NCM (Obrigatório):",
                value=dados[4] if dados[4] else "",
                placeholder="Ex: 8481.80.99",
            )
            nov_preco = st.number_input(
                "Preço Unitário (R$)",
                min_value=0.0,
                step=0.01,
                value=float(dados[9]),
            )
            nov_estante = st.text_input(
                "Estante", value=dados[5] if dados[5] else ""
            )
            nov_prateleira = st.text_input(
                "Prateleira", value=dados[6] if dados[6] else ""
            )
            nov_caixa = st.text_input(
                "Caixa / Posição", value=dados[7] if dados[7] else ""
            )
            nov_qtd = st.number_input(
                "Quantidade em Estoque",
                min_value=0,
                step=1,
                value=int(dados[8]),
            )

            btn_salvar_edit = st.form_submit_button("💾 SALVAR ALTERAÇÕES")

            if btn_salvar_edit:
                if not nov_ncm:
                    st.error("O campo NCM é obrigatório!")
                elif not validar_ncm(nov_ncm):
                    st.error(
                        "Formato do NCM inválido! Use o padrão de 8 dígitos com pontos (ex: 8481.80.99)."
                    )
                else:
                    conn_u = conectar_banco()
                    cursor_u = conn_u.cursor()
                    cursor_u.execute(
                        """
                        UPDATE estoque 
                        SET nome = ?, cod = ?, cod_ref = ?, ncm = ?, estante = ?, prateleira = ?, caixa = ?, quanti = ?, preco = ?
                        WHERE id = ?
                    """,
                        (
                            nov_nome,
                            nov_cod,
                            nov_ref,
                            nov_ncm.strip(),
                            nov_estante,
                            nov_prateleira,
                            nov_caixa,
                            nov_qtd,
                            nov_preco,
                            dados[0],
                        ),
                    )
                    conn_u.commit()
                    conn_u.close()

                    registrar_historico("EDIÇÃO", nov_nome, nov_qtd)
                    st.success("Informações e NCM atualizados com sucesso!")
                    st.rerun()
    else:
        st.info("Nenhum item disponível para edição.")

# =========================================================
# 5. VALORES DO ESTOQUE
# =========================================================
elif opcao == "💰 Valores do Estoque":
    st.title("💰 Análise Financeira do Estoque")

    conn = conectar_banco()
    df = pd.read_sql_query("SELECT nome, quanti, preco FROM estoque", conn)
    conn.close()

    if not df.empty:
        df["valor_total_item"] = df["quanti"] * df["preco"]
        valor_total_geral = df["valor_total_item"].sum()

        df_com_valor = df[df["valor_total_item"] > 0].copy()

        if not df_com_valor.empty:
            df_com_valor = df_com_valor.sort_values(
                by="valor_total_item", ascending=False
            )
            top_10 = df_com_valor.head(10).copy()
            outros_valor = df_com_valor.iloc[10:]["valor_total_item"].sum()

            if outros_valor > 0:
                top_10 = pd.concat(
                    [
                        top_10,
                        pd.DataFrame(
                            [
                                {
                                    "nome": "Outros Itens",
                                    "valor_total_item": outros_valor,
                                }
                            ]
                        ),
                    ],
                    ignore_index=True,
                )

            st.subheader("📊 Top 10 Itens de Maior Valor Acumulado no Estoque")
            fig = px.pie(
                top_10,
                values="valor_total_item",
                names="nome",
                hole=0.4,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(
                "Nenhum item possui preço cadastrado maior que R$ 0,00 para gerar o gráfico."
            )

        st.divider()
        st.metric(
            label="💵 VALOR TOTAL ACUMULADO EM ESTOQUE",
            value=f"R$ {valor_total_geral:,.2f}",
        )
    else:
        st.info("Nenhum item cadastrado no estoque.")

# =========================================================
# 6. ENTRADAS (REPOSIÇÃO)
# =========================================================
elif opcao == "📥 Entradas (Reposição)":
    st.title("📦 Reposição / Entrada de Estoque")

    lista_itens = obter_lista_itens()
    if lista_itens:
        item_selecionado = st.selectbox(
            "Selecione o Material:", options=lista_itens
        )
        qtd_add = st.number_input(
            "Quantidade a Adicionar:", min_value=1, step=1
        )

        if st.button("CONFIRMAR ENTRADA"):
            conn = conectar_banco()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, quanti FROM estoque WHERE nome = ?",
                (item_selecionado,),
            )
            res = cursor.fetchone()

            if res:
                item_id, quanti_atual = res
                nova_quanti = quanti_atual + qtd_add

                cursor.execute(
                    "UPDATE estoque SET quanti = ? WHERE id = ?",
                    (nova_quanti, item_id),
                )
                conn.commit()
                conn.close()

                registrar_historico("ENTRADA", item_selecionado, qtd_add)
                st.success(
                    f"Adicionadas +{qtd_add} unidades ao material '{item_selecionado}'. Saldo Atualizado: {nova_quanti} un."
                )
            else:
                conn.close()
                st.error("Erro ao localizar item.")
    else:
        st.info("Nenhum item cadastrado no estoque.")

# =========================================================
# 7. CADASTRAR ITEM
# =========================================================
elif opcao == "➕ Cadastrar Item":
    st.title("➕ Cadastrar Novo Material")

    with st.form("form_cadastro", clear_on_submit=True):
        nome = st.text_input("Nome do Material (Obrigatório):")
        cod = st.text_input("Código Interno (Opcional):")
        ref = st.text_input("Cód. REF (Opcional):")
        ncm = st.text_input(
            "NCM (Obrigatório):",
            placeholder="Ex: 8481.80.99",
        )
        preco = st.number_input(
            "Preço Unitário (R$):", min_value=0.0, step=0.01
        )
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
                st.error(
                    "Formato do NCM inválido! Utilize o padrão de 8 dígitos com pontos (ex: 8481.80.99)."
                )
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
                    st.success(
                        f"Material '{nome}' cadastrado com sucesso! Os campos foram limpos."
                    )
                except sqlite3.Error as e:
                    st.error(f"Erro ao salvar no banco: {e}")
                finally:
                    conn.close()

# =========================================================
# 8. HISTÓRICO (LOGS GERAIS)
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
    
