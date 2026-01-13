import streamlit as st
import requests
import os
import time
from datetime import datetime
import zipfile
import io

# Configuração da página
st.set_page_config(
    page_title="Download de Holerites - RD Station",
    page_icon="📄",
    layout="wide"
)

# CSS customizado
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .success-box {
        padding: 1rem;
        background-color: #d4edda;
        border-left: 4px solid #28a745;
        border-radius: 4px;
        margin: 1rem 0;
    }
    .info-box {
        padding: 1rem;
        background-color: #d1ecf1;
        border-left: 4px solid #17a2b8;
        border-radius: 4px;
        margin: 1rem 0;
    }
    .warning-box {
        padding: 1rem;
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        border-radius: 4px;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# Inicializa session state
if 'deals_filtrados' not in st.session_state:
    st.session_state.deals_filtrados = []
if 'holerites_baixados' not in st.session_state:
    st.session_state.holerites_baixados = []
if 'processando' not in st.session_state:
    st.session_state.processando = False

# Palavras-chave para holerites
PALAVRAS_CHAVE_HOLERITE = [
    "contra cheque", "holerite", "contracheque", "folha de pagamento",
    "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez",
    "janeiro", "fevereiro", "março", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
]

# Funções auxiliares
def fazer_requisicao_com_retry(url, headers, params=None, max_tentativas=3):
    """Faz requisição com retry automático"""
    for tentativa in range(max_tentativas):
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 429:
                wait_time = (tentativa + 1) * 5
                time.sleep(wait_time)
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            if tentativa == max_tentativas - 1:
                raise e
            time.sleep(2)
    return None

def eh_holerite(nome_arquivo):
    """Verifica se o arquivo é um holerite"""
    nome_lower = nome_arquivo.lower()
    return any(palavra.lower() in nome_lower for palavra in PALAVRAS_CHAVE_HOLERITE)

def buscar_organizations(token):
    """Busca todas as organizações"""
    url = "https://api.rd.services/crm/v2/organizations"
    headers = {"Authorization": f"Bearer {token}"}
    
    todas_orgs = []
    pagina = 1
    
    with st.spinner("Buscando organizações..."):
        while True:
            params = {"page[number]": pagina, "page[size]": 100}
            try:
                response = fazer_requisicao_com_retry(url, headers, params)
                if not response:
                    break
                
                dados = response.json()
                if 'data' not in dados or not dados['data']:
                    break
                
                todas_orgs.extend(dados['data'])
                
                if not dados.get('links', {}).get('next'):
                    break
                
                pagina += 1
                time.sleep(0.5)
            except Exception as e:
                st.error(f"Erro ao buscar organizações: {e}")
                break
    
    return todas_orgs

def buscar_pipelines(token):
    """Busca todos os pipelines"""
    url = "https://api.rd.services/crm/v2/pipelines"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = fazer_requisicao_com_retry(url, headers)
        if response:
            return response.json().get('data', [])
    except Exception as e:
        st.error(f"Erro ao buscar pipelines: {e}")
    return []

def buscar_stages(token, pipeline_id):
    """Busca os stages de um pipeline"""
    url = f"https://api.rd.services/crm/v2/pipelines/{pipeline_id}/stages"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = fazer_requisicao_com_retry(url, headers)
        if response:
            return response.json().get('data', [])
    except Exception as e:
        st.error(f"Erro ao buscar stages: {e}")
    return []

def listar_deals(token, pipeline_id=None, stage_id=None, organization_id=None):
    """Lista deals com filtros"""
    url = "https://api.rd.services/crm/v2/deals"
    headers = {"Authorization": f"Bearer {token}"}
    
    todos_deals = []
    pagina = 1
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while True:
        params = {"page[number]": pagina, "page[size]": 200}
        
        try:
            response = fazer_requisicao_com_retry(url, headers, params)
            if not response:
                break
            
            dados = response.json()
            if 'data' not in dados or not dados['data']:
                break
            
            deals_pagina = dados['data']
            todos_deals.extend(deals_pagina)
            
            status_text.text(f"Buscando deals... Página {pagina} ({len(todos_deals)} deals)")
            
            if not dados.get('links', {}).get('next'):
                break
            
            pagina += 1
            time.sleep(0.5)
            
        except Exception as e:
            st.error(f"Erro ao listar deals: {e}")
            break
    
    progress_bar.progress(100)
    status_text.text(f"✓ {len(todos_deals)} deals encontrados")
    
    # Aplica filtros
    deals_filtrados = todos_deals
    
    if pipeline_id:
        deals_filtrados = [d for d in deals_filtrados if d.get('pipeline_id') == pipeline_id]
    
    if stage_id:
        deals_filtrados = [d for d in deals_filtrados if d.get('stage_id') == stage_id]
    
    if organization_id:
        deals_filtrados = [d for d in deals_filtrados if d.get('organization_id') == organization_id]
    
    return deals_filtrados

def baixar_holerites_deal(token, deal_id):
    """Baixa holerites de um deal específico"""
    url = f"https://api.rd.services/crm/v2/deals/{deal_id}/files"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = fazer_requisicao_com_retry(url, headers)
        if not response:
            return []
        
        dados = response.json()
        arquivos = dados.get('data', [])
        
        holerites = []
        for arquivo in arquivos:
            nome = arquivo.get('name', '')
            if eh_holerite(nome):
                # Baixa o arquivo
                url_arquivo = arquivo.get('url')
                try:
                    resp = requests.get(url_arquivo, stream=True)
                    resp.raise_for_status()
                    
                    holerites.append({
                        'nome': nome,
                        'deal_id': deal_id,
                        'conteudo': resp.content,
                        'tamanho': len(resp.content)
                    })
                except Exception as e:
                    st.warning(f"Erro ao baixar {nome}: {e}")
        
        return holerites
    except Exception as e:
        return []

# Interface principal
st.markdown('<div class="main-header">📄 Download de Holerites - RD Station CRM</div>', unsafe_allow_html=True)

# Sidebar - Configurações
with st.sidebar:
    st.header("⚙️ Configurações")
    
    access_token = st.text_input(
        "Token de Acesso",
        type="password",
        value="YzXVJZGprpRkChgmodBjyimsqXNuYAqJ",
        help="Insira seu token de acesso do RD Station"
    )
    
    st.divider()
    
    if access_token:
        # Busca organizações
        if st.button("🔄 Carregar Organizações e Pipelines", use_container_width=True):
            with st.spinner("Carregando..."):
                st.session_state.organizations = buscar_organizations(access_token)
                st.session_state.pipelines = buscar_pipelines(access_token)
                st.success("✓ Dados carregados!")
        
        st.divider()
        
        # Filtro de Pipeline
        if 'pipelines' in st.session_state and st.session_state.pipelines:
            pipeline_options = {p['id']: p['name'] for p in st.session_state.pipelines}
            pipeline_selected = st.selectbox(
                "Pipeline",
                options=[''] + list(pipeline_options.keys()),
                format_func=lambda x: "Todos" if x == '' else pipeline_options.get(x, x)
            )
            
            # Filtro de Stage
            if pipeline_selected:
                stages = buscar_stages(access_token, pipeline_selected)
                if stages:
                    stage_options = {s['id']: s['name'] for s in stages}
                    stage_selected = st.selectbox(
                        "Stage",
                        options=[''] + list(stage_options.keys()),
                        format_func=lambda x: "Todos" if x == '' else stage_options.get(x, x)
                    )
                else:
                    stage_selected = None
            else:
                stage_selected = None
        else:
            pipeline_selected = None
            stage_selected = None
        
        # Filtro de Organização
        if 'organizations' in st.session_state and st.session_state.organizations:
            org_options = {o['id']: o['name'] for o in st.session_state.organizations}
            org_selected = st.selectbox(
                "Organização (Prefeitura)",
                options=[''] + list(org_options.keys()),
                format_func=lambda x: "Todas" if x == '' else org_options.get(x, x)
            )
        else:
            org_selected = None
        
        st.divider()
        
        max_deals = st.number_input(
            "Máximo de Deals",
            min_value=1,
            max_value=1000,
            value=200,
            help="Limite de deals para processar"
        )
    else:
        st.warning("⚠️ Insira o token de acesso")

# Área principal
col1, col2 = st.columns([2, 1])

with col1:
    st.header("🎯 Buscar e Baixar Holerites")
    
    if access_token:
        if st.button("🚀 Iniciar Busca de Deals", type="primary", use_container_width=True):
            st.session_state.processando = True
            
            # Busca deals
            deals = listar_deals(
                access_token,
                pipeline_id=pipeline_selected if pipeline_selected else None,
                stage_id=stage_selected if stage_selected else None,
                organization_id=org_selected if org_selected else None
            )
            
            # Limita quantidade
            deals = deals[:max_deals]
            
            st.session_state.deals_filtrados = deals
            st.session_state.processando = False
            
            if deals:
                st.markdown(f'<div class="success-box">✓ {len(deals)} deals encontrados e prontos para processamento!</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="warning-box">⚠️ Nenhum deal encontrado com os filtros aplicados</div>', unsafe_allow_html=True)
        
        # Mostra deals encontrados
        if st.session_state.deals_filtrados:
            st.divider()
            st.subheader(f"📋 {len(st.session_state.deals_filtrados)} Deals Encontrados")
            
            # Preview dos deals
            with st.expander("Ver lista de deals"):
                for i, deal in enumerate(st.session_state.deals_filtrados[:20], 1):
                    st.text(f"{i}. {deal.get('name', 'Sem nome')} (ID: {deal.get('id')})")
                if len(st.session_state.deals_filtrados) > 20:
                    st.text(f"... e mais {len(st.session_state.deals_filtrados) - 20} deals")
            
            st.divider()
            
            # Botão para baixar holerites
            if st.button("📥 Baixar Holerites dos Deals Selecionados", type="primary", use_container_width=True):
                st.session_state.holerites_baixados = []
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total_deals = len(st.session_state.deals_filtrados)
                
                for idx, deal in enumerate(st.session_state.deals_filtrados, 1):
                    deal_id = deal.get('id')
                    deal_name = deal.get('name', 'Sem nome')
                    
                    status_text.text(f"Processando {idx}/{total_deals}: {deal_name}")
                    
                    holerites = baixar_holerites_deal(access_token, deal_id)
                    st.session_state.holerites_baixados.extend(holerites)
                    
                    progress_bar.progress(idx / total_deals)
                    time.sleep(0.5)
                
                status_text.text(f"✓ Processamento concluído!")
                progress_bar.progress(100)
                
                if st.session_state.holerites_baixados:
                    st.markdown(f'<div class="success-box">🎉 {len(st.session_state.holerites_baixados)} holerites baixados com sucesso!</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="warning-box">⚠️ Nenhum holerite encontrado nos deals selecionados</div>', unsafe_allow_html=True)
    else:
        st.info("👈 Configure o token de acesso na barra lateral para começar")

with col2:
    st.header("📊 Estatísticas")
    
    # Métricas
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Deals", len(st.session_state.deals_filtrados))
    with col_b:
        st.metric("Holerites", len(st.session_state.holerites_baixados))
    
    if st.session_state.holerites_baixados:
        total_size = sum(h['tamanho'] for h in st.session_state.holerites_baixados)
        st.metric("Tamanho Total", f"{total_size / (1024*1024):.2f} MB")

# Área de download
if st.session_state.holerites_baixados:
    st.divider()
    st.header("📦 Download dos Holerites")
    
    # Cria ZIP com todos os holerites
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for holerite in st.session_state.holerites_baixados:
            nome_seguro = "".join(c for c in holerite['nome'] if c.isalnum() or c in (' ', '.', '_', '-'))
            nome_arquivo = f"{holerite['deal_id']}_{nome_seguro}"
            zip_file.writestr(nome_arquivo, holerite['conteudo'])
    
    zip_buffer.seek(0)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.download_button(
            label="⬇️ Baixar Todos os Holerites (ZIP)",
            data=zip_buffer.getvalue(),
            file_name=f"holerites_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
            use_container_width=True
        )
    
    # Lista de holerites baixados
    with st.expander(f"📋 Ver lista de {len(st.session_state.holerites_baixados)} holerites"):
        for i, holerite in enumerate(st.session_state.holerites_baixados, 1):
            tamanho_kb = holerite['tamanho'] / 1024
            st.text(f"{i}. {holerite['nome']} ({tamanho_kb:.1f} KB) - Deal: {holerite['deal_id']}")

# Footer
st.divider()
st.markdown("""
    <div style="text-align: center; color: #666; padding: 1rem;">
        💡 <b>Dica:</b> Use os filtros na barra lateral para encontrar deals específicos<br>
        📄 Os holerites são identificados automaticamente por palavras-chave no nome do arquivo
    </div>
""", unsafe_allow_html=True)
