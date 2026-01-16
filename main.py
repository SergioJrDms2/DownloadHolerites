import streamlit as st
import requests
import os
import time
from datetime import datetime, timedelta
import zipfile
import io
import json

# Configuração da página
st.set_page_config(
    page_title="Download de Holerites - RD Station",
    page_icon="📄",
    layout="wide"
)

# Configurações OAuth2
CLIENT_ID = "ab2a1942-d61d-436b-a41d-0d1adb6f9ee7"
CLIENT_SECRET = "56ea6d7b4b53405185bceee354219835"
TOKEN_FILE = "rd_tokens.json"

# Detecta automaticamente a URL do Streamlit
def get_redirect_uri():
    """Detecta a URL atual do Streamlit"""
    try:
        # Tenta pegar do headers
        headers = st.context.headers
        if headers and 'host' in headers:
            host = headers['host']
            # Verifica se é HTTPS ou HTTP
            protocol = 'https' if '443' in str(headers.get('x-forwarded-port', '')) or 'github.dev' in host else 'http'
            return f"{protocol}://{host}"
    except:
        pass
    
    # Fallback para localhost
    return "http://localhost:8501"

REDIRECT_URI = "https://fluffy-tribble-7xr6pgw96pj2pvxq-8501.app.github.dev/"

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
    .code-box {
        background-color: #f4f4f4;
        padding: 0.5rem;
        border-radius: 4px;
        font-family: monospace;
        border: 1px solid #ddd;
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
        
        if expiry > datetime.now() + timedelta(minutes=5):
            st.session_state.access_token = tokens['access_token']
            st.session_state.token_expiry = expiry
            return tokens
        else:
            return refresh_access_token(tokens['refresh_token'])
    except Exception as e:
        st.error(f"Erro ao carregar tokens: {e}")
        return None

def obter_access_token(authorization_code):
    """Obtém access token usando o código de autorização"""
    url = "https://api.rd.services/oauth2/token"
    
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': authorization_code,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        
        if response.status_code != 200:
            st.error(f"❌ Status: {response.status_code}")
            st.error(f"Resposta: {response.text}")
            return None
        
        data = response.json()
        
        salvar_tokens(
            data['access_token'],
            data['refresh_token'],
            data['expires_in']
        )
        
        return data
    except Exception as e:
        st.error(f"❌ Erro ao obter access token: {e}")
        if hasattr(e, 'response'):
            st.error(f"Resposta: {e.response.text}")
        return None

def refresh_access_token(refresh_token):
    """Atualiza o access token usando refresh token"""
    url = "https://api.rd.services/oauth2/token"
    
    payload = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token'
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    try:
        response = requests.post(url, data=payload, headers=headers)
        
        if response.status_code != 200:
            if os.path.exists(TOKEN_FILE):
                os.remove(TOKEN_FILE)
            st.session_state.access_token = None
            st.session_state.token_expiry = None
            return None
        
        data = response.json()
        
        salvar_tokens(
            data['access_token'],
            data['refresh_token'],
            data['expires_in']
        )
        
        return data
    except Exception as e:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        st.session_state.access_token = None
        st.session_state.token_expiry = None
        return None

def verificar_e_renovar_token():
    """Verifica se o token precisa ser renovado"""
    if not st.session_state.token_expiry:
        return False
    
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

def eh_holerite(nome_arquivo: str) -> bool:
    nome = nome_arquivo.lower().strip()

    # 1️⃣ Obrigatoriamente PDF
    if not nome.endswith('.pdf'):
        return False

    # 2️⃣ Precisa conter alguma palavra-chave
    return any(palavra in nome for palavra in PALAVRAS_CHAVE_HOLERITE)


def buscar_organizations(token):
    """Busca todas as organizações"""
    url = "https://api.rd.services/crm/v2/organizations"
    headers = {"Authorization": f"Bearer {token}"}
    
    todas_orgs = []
    pagina = 1
    
    with st.spinner("🔍 Buscando organizações..."):
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
                st.error(f"❌ Erro ao buscar organizações: {e}")
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
        st.error(f"❌ Erro ao buscar pipelines: {e}")
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
        st.error(f"❌ Erro ao buscar stages: {e}")
    return []

def _rdql_or(field, values):
    values = [v for v in (values or []) if v]
    if not values:
        return None
    if len(values) == 1:
        return f"{field}:{values[0]}"
    return "(" + " OR ".join(f"{field}:{v}" for v in values) + ")"

def _rdql_and(parts):
    parts = [p for p in (parts or []) if p]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return " AND ".join(parts)

def build_deals_rdql_filter(pipeline_id=None, stage_ids=None, organization_ids=None):
    parts = []
    if pipeline_id:
        parts.append(f"pipeline_id:{pipeline_id}")
    parts.append(_rdql_or("stage_id", stage_ids))
    parts.append(_rdql_or("organization_id", organization_ids))
    return _rdql_and(parts)

def listar_deals(
    token,
    pipeline_id=None,
    stage_ids=None,         
    organization_ids=None,   
    max_paginas=10,
    max_deals=None
):
    url = "https://api.rd.services/crm/v2/deals"
    headers = {"Authorization": f"Bearer {token}"}

    api_filter_full = build_deals_rdql_filter(
        pipeline_id=pipeline_id,
        stage_ids=stage_ids,
        organization_ids=organization_ids
    )

    api_filter_pipeline = f"pipeline_id:{pipeline_id}" if pipeline_id else None

    api_filter = api_filter_full

    if stage_ids and len(stage_ids) > 6:
        api_filter = api_filter_pipeline

    if organization_ids and len(organization_ids) > 6:
        api_filter = api_filter_pipeline

    if api_filter and len(api_filter) > 900:
        api_filter = api_filter_pipeline

    deals_filtrados = []
    pagina = 1

    progress_bar = st.progress(0)
    status_text = st.empty()

    max_paginas_efetivo = min(max_paginas, 100)
    filtro_server_side_desativado = False
    while pagina <= max_paginas_efetivo:
        params = {
            "page[number]": pagina,
            "page[size]": 100
        }

        if api_filter and not filtro_server_side_desativado:
            params["filter"] = api_filter

        try:
            response = fazer_requisicao_com_retry(url, headers, params)
            if not response:
                break

            dados = response.json()
            deals_pagina = dados.get('data', [])

            if not deals_pagina:
                break

            deals_pagina_filtrada = deals_pagina

            if pipeline_id and api_filter != f"pipeline_id:{pipeline_id}":
                deals_pagina_filtrada = [
                    d for d in deals_pagina_filtrada
                    if d.get('pipeline_id') == pipeline_id
                ]

            if stage_ids:
                stage_ids_set = set(stage_ids)
                deals_pagina_filtrada = [
                    d for d in deals_pagina_filtrada
                    if d.get('stage_id') in stage_ids_set
                ]

            if organization_ids:
                org_ids_set = set(organization_ids)
                deals_pagina_filtrada = [
                    d for d in deals_pagina_filtrada
                    if d.get('organization_id') in org_ids_set
                    if d.get('organization_id') is not None
                ]

            deals_filtrados.extend(deals_pagina_filtrada)

            status_text.text(
                f"🔍 Buscando deals... Página {pagina}/{max_paginas} "
                f"({len(deals_filtrados)} deals)"
            )

            if max_deals and len(deals_filtrados) >= max_deals:
                break

            if not dados.get('links', {}).get('next'):
                break

            pagina += 1
            time.sleep(0.4)
            progress_bar.progress(min(pagina / max_paginas_efetivo, 1.0))

        except requests.exceptions.HTTPError as e:
            status_code = getattr(getattr(e, 'response', None), 'status_code', None)

            if api_filter and not filtro_server_side_desativado and (status_code in (400, 414) or (status_code and status_code >= 500)):
                filtro_server_side_desativado = True
                st.warning("⚠️ A API falhou ao processar o filtro RDQL. Continuando com filtro local.")
                continue

            st.error(f"❌ Erro ao listar deals: {e}")
            break
        except Exception as e:
            st.error(f"❌ Erro ao listar deals: {e}")
            break

    progress_bar.progress(100)
    status_text.text(f"✅ {len(deals_filtrados)} deals carregados")

    if max_deals:
        return deals_filtrados[:max_deals]
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
                    st.warning(f"⚠️ Erro ao baixar {nome}: {e}")
        
        return holerites
    except Exception as e:
        return []

st.markdown('<div class="main-header">📄 Download de Holerites - RD Station CRM</div>', unsafe_allow_html=True)

query_params = st.query_params
if 'code' in query_params and not st.session_state.access_token:
    code = query_params['code']
    
    with st.spinner("🔄 Processando autorização automaticamente..."):
        resultado = obter_access_token(code)
        
    if resultado:
        st.success("✅ Autenticação realizada com sucesso!")
        st.query_params.clear()
        time.sleep(1)
        st.rerun()
    else:
        st.error("❌ Erro na autenticação.")

if not st.session_state.access_token:
    carregar_tokens()

if not st.session_state.access_token:
    auth_url = get_authorization_url()
    st.markdown(f"[🔐 Clique aqui para autenticar]({auth_url})")
    st.stop()

col1, col2 = st.columns([2, 1])

with col1:
    st.header("🔎 Filtros")
    
    pipelines = buscar_pipelines(st.session_state.access_token)
    pipeline_map = {p.get('name', p.get('id')): p.get('id') for p in pipelines}
    pipeline_names = ["(Todos)"] + sorted(pipeline_map.keys())
    pipeline_name = st.selectbox("Pipeline", pipeline_names)
    pipeline_selected = None if pipeline_name == "(Todos)" else pipeline_map.get(pipeline_name)
    
    stages = buscar_stages(st.session_state.access_token, pipeline_selected) if pipeline_selected else []
    stage_map = {s.get('name', s.get('id')): s.get('id') for s in stages}
    stage_names = sorted(stage_map.keys())
    stage_selected_names = st.multiselect("Estágio", stage_names)
    stage_selected = [stage_map[n] for n in stage_selected_names] if stage_selected_names else None

    if 'orgs_cache' not in st.session_state:
        st.session_state.orgs_cache = []

    if not st.session_state.orgs_cache:
        orgs = buscar_organizations(st.session_state.access_token)
        if orgs:
            st.session_state.orgs_cache = orgs

    orgs = st.session_state.orgs_cache
    org_id_to_name = {
        o.get('id'): (o.get('name') or o.get('id'))
        for o in orgs
        if o.get('id')
    }
    org_ids = sorted(org_id_to_name.keys(), key=lambda oid: (org_id_to_name.get(oid) or '').lower())
    org_selected = st.multiselect(
        "Organização",
        org_ids,
        format_func=lambda oid: org_id_to_name.get(oid, oid),
        key="org_selected_ids"
    )
    
    max_paginas = st.number_input("Máx. páginas", min_value=1, max_value=100, value=10)
    max_deals = st.number_input("Máx. deals", min_value=1, value=200)
    
    if st.button("🚀 Buscar Deals", type="primary", use_container_width=True):
        verificar_e_renovar_token()
        
        deals = listar_deals(
            st.session_state.access_token,
            pipeline_id=pipeline_selected if pipeline_selected else None,
            stage_ids=stage_selected if stage_selected else None,
            organization_ids=org_selected if org_selected else None,
            max_paginas=max_paginas,
            max_deals=max_deals
        )
        st.session_state.deals_filtrados = deals
        st.session_state.holerites_baixados = []

    if st.session_state.deals_filtrados:
        st.divider()
        st.subheader(f"📋 {len(st.session_state.deals_filtrados)} Deals")
        
        with st.expander("Ver lista"):
            for i, deal in enumerate(st.session_state.deals_filtrados[:20], 1):
                st.text(f"{i}. {deal.get('name', 'Sem nome')}")
            if len(st.session_state.deals_filtrados) > 20:
                st.text(f"... +{len(st.session_state.deals_filtrados) - 20}")
        
        st.divider()
        
        if st.button("📥 Baixar Holerites", type="primary", use_container_width=True):
            verificar_e_renovar_token()
            st.session_state.holerites_baixados = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            total = len(st.session_state.deals_filtrados)
            
            for idx, deal in enumerate(st.session_state.deals_filtrados, 1):
                status_text.text(f"📄 {idx}/{total}: {deal.get('name', 'Sem nome')}")
                
                holerites = baixar_holerites_deal(st.session_state.access_token, deal.get('id'))
                st.session_state.holerites_baixados.extend(holerites)
                
                progress_bar.progress(idx / total)
                time.sleep(0.5)
            
            status_text.text(f"✅ Concluído!")
            progress_bar.progress(100)
            
            if st.session_state.holerites_baixados:
                st.markdown(f'<div class="success-box">🎉 {len(st.session_state.holerites_baixados)} holerites baixados!</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="warning-box">⚠️ Nenhum holerite encontrado</div>', unsafe_allow_html=True)

with col2:
    st.header("📊 Estatísticas")
    st.metric("Deals", len(st.session_state.deals_filtrados))
    st.metric("Holerites", len(st.session_state.holerites_baixados))
    
    if st.session_state.holerites_baixados:
        total_size = sum(h['tamanho'] for h in st.session_state.holerites_baixados)
        st.metric("Tamanho", f"{total_size / (1024*1024):.2f} MB")

# Download
if st.session_state.holerites_baixados:
    st.divider()
    st.header("📦 Download")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for h in st.session_state.holerites_baixados:
            nome_seguro = "".join(c for c in h['nome'] if c.isalnum() or c in (' ', '.', '_', '-'))
            zip_file.writestr(f"{h['deal_id']}_{nome_seguro}", h['conteudo'])
    
    zip_buffer.seek(0)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.download_button(
            label="⬇️ Baixar Todos (ZIP)",
            data=zip_buffer.getvalue(),
            file_name=f"holerites_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
            use_container_width=True
        )
    
    with st.expander(f"📋 Lista de {len(st.session_state.holerites_baixados)} arquivos"):
        for i, h in enumerate(st.session_state.holerites_baixados, 1):
            st.text(f"{i}. {h['nome']} ({h['tamanho']/1024:.1f} KB)")

# Footer
st.divider()
st.markdown("""
    <div style="text-align: center; color: #666; padding: 1rem;">
        🔒 Tokens armazenados localmente • 🔄 Renovação automática • ⚡ Processo automático
    </div>
""", unsafe_allow_html=True)
