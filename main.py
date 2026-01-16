import streamlit as st
import requests
import os
import time
from datetime import datetime, timedelta
import zipfile
import io
import json
from pathlib import Path

# Configuração da página
st.set_page_config(
    page_title="Download de Holerites - RD Station",
    page_icon="📄",
    layout="wide"
)

# Configurações OAuth2
CLIENT_ID = "43462960-54de-43a7-b09c-ba3e6df8c558"
CLIENT_SECRET = st.secrets.get("RD_CLIENT_SECRET", "")  # Coloque no secrets.toml
REDIRECT_URI = "http://localhost:8501"  # Porta padrão do Streamlit
TOKEN_FILE = "rd_tokens.json"

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
    .error-box {
        padding: 1rem;
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
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
if 'access_token' not in st.session_state:
    st.session_state.access_token = None
if 'token_expiry' not in st.session_state:
    st.session_state.token_expiry = None

# Palavras-chave para holerites
PALAVRAS_CHAVE_HOLERITE = [
    "contra cheque", "holerite", "contracheque", "folha de pagamento",
    "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez",
    "janeiro", "fevereiro", "março", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
]

# ==================== FUNÇÕES DE AUTENTICAÇÃO ====================

def salvar_tokens(access_token, refresh_token, expires_in):
    """Salva os tokens em arquivo JSON"""
    tokens = {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'expires_at': (datetime.now() + timedelta(seconds=expires_in)).isoformat()
    }
    
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f)
    
    # Atualiza session state
    st.session_state.access_token = access_token
    st.session_state.token_expiry = datetime.fromisoformat(tokens['expires_at'])

def carregar_tokens():
    """Carrega tokens do arquivo"""
    if not os.path.exists(TOKEN_FILE):
        return None
    
    try:
        with open(TOKEN_FILE, 'r') as f:
            tokens = json.load(f)
        
        expiry = datetime.fromisoformat(tokens['expires_at'])
        
        # Verifica se o token ainda é válido (com margem de 5 minutos)
        if expiry > datetime.now() + timedelta(minutes=5):
            st.session_state.access_token = tokens['access_token']
            st.session_state.token_expiry = expiry
            return tokens
        else:
            # Token expirado, tenta refresh
            return refresh_access_token(tokens['refresh_token'])
    except Exception as e:
        st.error(f"Erro ao carregar tokens: {e}")
        return None

def obter_access_token(authorization_code):
    """Obtém access token usando o código de autorização"""
    url = "https://api.rd.services/auth/token"
    
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': authorization_code,
        'redirect_uri': REDIRECT_URI
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        data = response.json()
        
        salvar_tokens(
            data['access_token'],
            data['refresh_token'],
            data['expires_in']
        )
        
        return data
    except Exception as e:
        st.error(f"Erro ao obter access token: {e}")
        if hasattr(e, 'response'):
            st.error(f"Resposta: {e.response.text}")
        return None

def refresh_access_token(refresh_token):
    """Atualiza o access token usando refresh token"""
    url = "https://api.rd.services/auth/token"
    
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': refresh_token
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        data = response.json()
        
        salvar_tokens(
            data['access_token'],
            data['refresh_token'],
            data['expires_in']
        )
        
        st.success("✓ Token atualizado com sucesso!")
        return data
    except Exception as e:
        st.error(f"Erro ao atualizar token: {e}")
        if hasattr(e, 'response'):
            st.error(f"Resposta: {e.response.text}")
        # Remove tokens inválidos
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        st.session_state.access_token = None
        st.session_state.token_expiry = None
        return None

def verificar_e_renovar_token():
    """Verifica se o token precisa ser renovado e renova se necessário"""
    if not st.session_state.token_expiry:
        return False
    
    # Se faltam menos de 10 minutos para expirar, renova
    if st.session_state.token_expiry < datetime.now() + timedelta(minutes=10):
        tokens = carregar_tokens()
        return tokens is not None
    
    return True

def get_authorization_url():
    """Gera URL de autorização"""
    return f"https://accounts.rdstation.com/oauth/authorize?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"

# ==================== FUNÇÕES DA API ====================

def fazer_requisicao_com_retry(url, headers, params=None, max_tentativas=3):
    """Faz requisição com retry automático"""
    for tentativa in range(max_tentativas):
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 401:
                # Token expirado, tenta renovar
                st.warning("Token expirado, renovando...")
                tokens = carregar_tokens()
                if tokens:
                    headers["Authorization"] = f"Bearer {st.session_state.access_token}"
                    continue
                else:
                    raise Exception("Não foi possível renovar o token")
            
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

# ==================== INTERFACE PRINCIPAL ====================

st.markdown('<div class="main-header">📄 Download de Holerites - RD Station CRM</div>', unsafe_allow_html=True)

# Verifica se há código de autorização na URL
query_params = st.query_params
if 'code' in query_params and not st.session_state.access_token:
    code = query_params['code']
    st.info("🔄 Processando autorização...")
    resultado = obter_access_token(code)
    if resultado:
        st.success("✅ Autenticação realizada com sucesso!")
        # Limpa o código da URL
        st.query_params.clear()
        st.rerun()
    else:
        st.error("❌ Erro na autenticação. Tente novamente.")

# Tenta carregar tokens salvos
if not st.session_state.access_token:
    tokens = carregar_tokens()
    if tokens:
        st.success("✅ Token carregado automaticamente!")

# Sidebar - Autenticação
with st.sidebar:
    st.header("🔐 Autenticação")
    
    if st.session_state.access_token:
        st.success("✅ Autenticado")
        
        if st.session_state.token_expiry:
            tempo_restante = st.session_state.token_expiry - datetime.now()
            horas = int(tempo_restante.total_seconds() // 3600)
            minutos = int((tempo_restante.total_seconds() % 3600) // 60)
            st.info(f"⏱️ Token expira em: {horas}h {minutos}m")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Renovar Token", use_container_width=True):
                tokens = carregar_tokens()
        with col2:
            if st.button("🚪 Sair", use_container_width=True):
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                st.session_state.access_token = None
                st.session_state.token_expiry = None
                st.rerun()
    else:
        st.warning("⚠️ Não autenticado")
        
        st.markdown("### Como autenticar:")
        st.markdown("1. Clique no botão abaixo")
        st.markdown("2. Faça login no RD Station")
        st.markdown("3. Autorize o aplicativo")
        st.markdown("4. Você será redirecionado de volta")
        
        auth_url = get_authorization_url()
        st.markdown(f'<a href="{auth_url}" target="_blank"><button style="width:100%; padding:0.5rem; background-color:#1f77b4; color:white; border:none; border-radius:4px; cursor:pointer;">🔑 Autorizar no RD Station</button></a>', unsafe_allow_html=True)
        
        st.divider()
        
        # Opção manual (fallback)
        with st.expander("⚙️ Configuração Manual (Avançado)"):
            manual_token = st.text_input(
                "Access Token Manual",
                type="password",
                help="Use apenas se a autenticação OAuth não funcionar"
            )
            if manual_token and st.button("Usar Token Manual"):
                st.session_state.access_token = manual_token
                st.session_state.token_expiry = datetime.now() + timedelta(hours=24)
                st.rerun()
    
    st.divider()
    
    # Configurações de busca (apenas se autenticado)
    if st.session_state.access_token:
        st.header("⚙️ Filtros de Busca")
        
        # Verifica e renova token se necessário
        verificar_e_renovar_token()
        
        if st.button("🔄 Carregar Organizações e Pipelines", use_container_width=True):
            with st.spinner("Carregando..."):
                st.session_state.organizations = buscar_organizations(st.session_state.access_token)
                st.session_state.pipelines = buscar_pipelines(st.session_state.access_token)
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
                stages = buscar_stages(st.session_state.access_token, pipeline_selected)
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

# Área principal
if not st.session_state.access_token:
    st.markdown('<div class="info-box">👈 Faça login usando a barra lateral para começar</div>', unsafe_allow_html=True)
else:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("🎯 Buscar e Baixar Holerites")
        
        if st.button("🚀 Iniciar Busca de Deals", type="primary", use_container_width=True):
            verificar_e_renovar_token()
            st.session_state.processando = True
            
            # Busca deals
            deals = listar_deals(
                st.session_state.access_token,
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
                verificar_e_renovar_token()
                st.session_state.holerites_baixados = []
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                total_deals = len(st.session_state.deals_filtrados)
                
                for idx, deal in enumerate(st.session_state.deals_filtrados, 1):
                    deal_id = deal.get('id')
                    deal_name = deal.get('name', 'Sem nome')
                    
                    status_text.text(f"Processando {idx}/{total_deals}: {deal_name}")
                    
                    holerites = baixar_holerites_deal(st.session_state.access_token, deal_id)
                    st.session_state.holerites_baixados.extend(holerites)
                    
                    progress_bar.progress(idx / total_deals)
                    time.sleep(0.5)
                
                status_text.text(f"✓ Processamento concluído!")
                progress_bar.progress(100)
                
                if st.session_state.holerites_baixados:
                    st.markdown(f'<div class="success-box">🎉 {len(st.session_state.holerites_baixados)} holerites baixados com sucesso!</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="warning-box">⚠️ Nenhum holerite encontrado nos deals selecionados</div>', unsafe_allow_html=True)
    
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
        🔐 <b>Segurança:</b> Seus tokens são armazenados localmente e renovados automaticamente<br>
        💡 <b>Dica:</b> Use os filtros na barra lateral para encontrar deals específicos<br>
        📄 Os holerites são identificados automaticamente por palavras-chave no nome do arquivo
    </div>
""", unsafe_allow_html=True)