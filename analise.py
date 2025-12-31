import requests
import google.generativeai as genai
import time
import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta, time as dt_time
import re
import io

# --- 1. CONFIGURAÇÕES ---
st.set_page_config(page_title="Analise de conversas", page_icon="💎", layout="wide") 

def check_password(): # Função para verificar a senha de acesso à aplicação Streamlit
    """Retorna True se o usuário tiver a senha correta."""

    def password_entered(): # Função para verificar se a senha inserida bate com a do segredo.
        """Verifica se a senha inserida bate com a do segredo."""
        if st.session_state["password"] == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # Não armazena a senha na memória
        else:
            st.session_state["password_correct"] = False

    # Se já validou, retorna True
    if st.session_state.get("password_correct", False):
        return True

    # Interface de Login
    st.title("🔒 Acesso Restrito")
    st.text_input(
        "Digite a senha de acesso:", 
        type="password", 
        on_change=password_entered, 
        key="password"
    )
    
    if "password_correct" in st.session_state:
        st.error("😕 Senha incorreta.")
    
    return False

if not check_password():
    st.stop()  # 🛑 PARA TUDO AQUI SE NÃO TIVER LOGADO

try:
    INTERCOM_TOKEN = st.secrets["INTERCOM_TOKEN"] # Token de acesso à API do Intercom
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"] # Chave da API do Google Gemini
    INTERCOM_APP_ID = st.secrets["INTERCOM_APP_ID"] # ID do aplicativo Intercom
except:
    st.error("❌ Configure as chaves no secrets.toml") #    Arquivo secrets.toml deve conter INTERCOM_TOKEN, GEMINI_API_KEY e INTERCOM_APP_ID  
    st.stop()

genai.configure(api_key=GEMINI_API_KEY) # Configuração da API Gemini
model = genai.GenerativeModel('gemma-3-12b-it') # Modelo Gemini a ser usado

# Inicializa variável de sessão para armazenar resultados
if 'df_resultado' not in st.session_state: # Variável para armazenar o DataFrame de resultados
    st.session_state['df_resultado'] = None # Inicializa como None

# --- 2. FUNÇÕES AUXILIARES ---

def fazer_requisicao_segura(method, url, json=None, params=None, max_retries=5): # Função para fazer requisições HTTP com tratamento de erros e rate limiting
    headers = { #   Cabeçalhos HTTP - API
        "Authorization": f"Bearer {INTERCOM_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    for attempt in range(max_retries): # Tenta fazer a requisição várias vezes em caso de falha
        try: # Dependendo do método, faz a requisição apropriada
            if method == "POST": # POST request
                resp = requests.post(url, json=json, headers=headers) # Faz requisição POST
            else: # GET request
                resp = requests.get(url, params=params, headers=headers) # Faz requisição GET
            
            if resp.status_code == 200: # Se a resposta for bem-sucedida, retorna o JSON
                return resp.json() # Retorna o JSON da resposta
            elif resp.status_code == 429: # Se atingir o limite de requisições, aguarda o tempo necessário
                wait = int(resp.headers.get("X-RateLimit-Reset", time.time() + 2)) - int(time.time()) + 2 # Calcula o tempo de espera
                wait = max(2, wait) # Garante um tempo mínimo de espera
                st.toast(f"⏳ Aguardando {wait}s (Rate Limit)...", icon="🛑") 
                time.sleep(wait)
                continue # Tenta novamente após o tempo de espera
            else:
                return None # Em caso de outros erros, retorna None
        except Exception: # Em caso de exceção, aguarda um pouco antes de tentar novamente
            time.sleep(2) # Espera 2 segundos antes de tentar novamente
    return None

def chamar_gemini_seguro(prompt):# Função para chamar o modelo Gemini com tratamento de erros
    for attempt in range(3): # Tenta chamar o modelo várias vezes em caso de falha
        try: # Tenta gerar o conteúdo com o modelo
            response = model.generate_content(prompt) # Gera o conteúdo usando o modelo Gemini
            return response.text # Retorna o texto gerado
        except: # Em caso de exceção, aguarda um tempo exponencial antes de tentar novamente
            time.sleep(2 ** (attempt + 1)) # Espera exponencialmente mais tempo a cada tentativa    
    return "Falha na análise da IA." # Retorna mensagem de falha após várias tentativas

def extrair_nota_automacao(texto_automacao): # Função para extrair a nota de automação do texto
    match = re.search(r'\b(10|[0-9])\b', str(texto_automacao)) # Procura por um número entre 0 e 10 no texto 
    if match: return int(match.group(1)) # Retorna a nota encontrada
    return 0 # Retorna 0 se nenhuma nota for encontrada

def processar_resposta_texto(texto): # Função para processar a resposta de texto da IA e extrair campos específicos
    dados = { # Dicionário para armazenar os dados extraídos
        "Motivo": "Não identificado", "Qtd Problemas": "", "Dúvidas": "", # Campos padrão
        "Ação": "", "Falta Contato": "", "Automação Texto": "", 
        "Nota Automação": 0, "Melhoria": ""
    }
    padroes = { # Padrões regex para extrair cada campo
        "Motivo": r"1\.\s*\**.*? contato\**\s*:?\s*(.*?)(?=\n\s*2\.|\n\s*\**2\.)", # Regex para extrair o motivo do contato
        "Qtd Problemas": r"2\.\s*\**.*? problemas\**\s*:?\s*(.*?)(?=\n\s*3\.|\n\s*\**3\.)",# Regex para extrair a quantidade de problemas relatados
        "Dúvidas": r"3\.\s*\**.*? dúvidas\**\s*:?\s*(.*?)(?=\n\s*4\.|\n\s*\**4\.)", # Regex para extrair as dúvidas ou reclamações principais
        "Ação": r"4\.\s*\**.*? agente\**\s*:?\s*(.*?)(?=\n\s*5\.|\n\s*\**5\.)", # Regex para extrair a ação do agente
        "Falta Contato": r"5\.\s*\**.*? falta de contato\**\s*:?\s*(.*?)(?=\n\s*6\.|\n\s*\**6\.)", # Regex para extrair se foi finalizada por falta de contato
        "Automação Texto": r"6\.\s*\**.*? automação\**\s*:?\s*(.*?)(?=\n\s*7\.|\n\s*\**7\.)", # Regex para extrair o texto sobre potencial de automação
        "Melhoria": r"7\.\s*\**.*? melhoria\**\s*:?\s*(.*?)(?=$)"
    }
    for chave, regex in padroes.items(): # Itera sobre os padrões para extrair cada campo
        match = re.search(regex, texto, re.DOTALL | re.IGNORECASE) # Procura o padrão no texto
        if match: # Se encontrar uma correspondência, limpa e armazena o valor
            dados[chave] = match.group(1).strip().replace("**", "").replace("`", "") # Limpa o texto extraído
    
    if dados["Automação Texto"]: # Extrai a nota de automação se o texto estiver presente
        dados["Nota Automação"] = extrair_nota_automacao(dados["Automação Texto"]) # Extrai a nota de automação do texto
    return dados # Retorna o dicionário com os dados extraídos

# --- 3. FUNÇÕES PRINCIPAIS ---
@st.cache_data(show_spinner=False) # Cacheia o resultado para evitar recarregamentos desnecessários
def carregar_tags(): # Função para carregar as tags do arquivo Excel gerado anteriormente
    try: # Tenta ler o arquivo Excel e criar um dicionário de tags
        df = pd.read_excel("tags_intercom.xlsx") # Lê o arquivo Excel com as tags
        df['ID da Tag'] = df['ID da Tag'].astype(str) # Garante que os IDs sejam strings
        return dict(zip(df["Nome da Tag"].astype(str).str.strip(), df["ID da Tag"])) # Retorna um dicionário mapeando nomes de tags para IDs
    except: return {} # Retorna um dicionário vazio em caso de erro

def buscar_conversas(lista_ids, d_inicio, d_fim): # Função para buscar conversas no Intercom com base em tags e intervalo de datas
    url = "https://api.intercom.io/conversations/search" # URL da API de busca de conversas
    ts_i = int(datetime.combine(d_inicio, dt_time.min).replace(tzinfo=timezone.utc).timestamp()) # Timestamp de início
    ts_f = int(datetime.combine(d_fim, dt_time.max).replace(tzinfo=timezone.utc).timestamp()) # Timestamp de fim
    
    conversas = [] # Lista para armazenar as conversas encontradas
    payload = { # Payload da requisição de busca
        "query": { # Consulta com filtros
            "operator": "AND", # Operador AND para combinar filtros
            "value": [ # Filtros específicos
                {"field": "tag_ids", "operator": "IN", "value": lista_ids}, # Filtro por tags
                {"field": "created_at", "operator": ">", "value": ts_i}, # Filtro por data de início
                {"field": "created_at", "operator": "<", "value": ts_f} # Filtro por data de fim
            ]
        },
        "pagination": {"per_page": 50}, # Configuração de paginação
        "sort": {"field": "created_at", "order": "desc"} # Ordenação por data de criação decrescente
    }
    
    while True: # Loop para paginar através dos resultados
        data = fazer_requisicao_segura("POST", url, json=payload) # Faz a requisição segura
        if not data: break # Sai do loop se não houver dados
        conversas.extend(data.get('conversations', [])) # Adiciona as conversas encontradas à lista
        pag = data.get('pages', {}) # Obtém informações de paginação
        if pag.get('next'): #   Se houver uma próxima página, atualiza o payload para buscar a próxima página
            payload['pagination']['starting_after'] = pag['next']['starting_after'] # Atualiza o cursor de paginação
        else: break # Sai do loop se não houver mais páginas
    return conversas # Retorna a lista de conversas encontradas

def ler_conversa_completa(c_id): # Função para ler a conversa completa de um ticket específico
    data = fazer_requisicao_segura("GET", f"https://api.intercom.io/conversations/{c_id}") # Faz a requisição segura para obter a conversa
    if not data: return "" # Retorna string vazia em caso de erro
    txt = f"INÍCIO: {data.get('source', {}).get('body', '')}\n" # Inicia o texto com a mensagem inicial da conversa
    for p in data.get('conversation_parts', {}).get('conversation_parts', []): # Itera sobre as partes da conversa
        if p.get('body'): #     Se houver corpo na parte da conversa, adiciona ao texto
            role = "CLIENTE" if p.get('author', {}).get('type') in ['user','lead'] else "AGENTE" # Determina o papel do autor
            txt += f"{role}: {p['body']}\n" # Adiciona a parte da conversa ao texto
    return re.sub(r'<[^>]+>', ' ', txt) # Remove tags HTML do texto e retorna o texto limpo
# --- 4. INTERFACE STREAMLIT ---
st.title("📊 Analise de conversas")

# Container para o topo da página
top_container = st.container()
# Carrega as tags do arquivo Excel
tags_map = carregar_tags()

with st.sidebar: # Barra lateral para filtros e controles
    st.header("Filtros") # Cabeçalho da barra lateral
    tags_sel = st.multiselect("Tags:", list(tags_map.keys()) if tags_map else []) # Seleção múltipla de tags
    ids_sel = [tags_map[t] for t in tags_sel] # Obtém os IDs das tags selecionadas
    st.divider() # Linha divisória
    d1 = st.date_input("Início", datetime.now()-timedelta(days=7)) # Input de data de início
    d2 = st.date_input("Fim", datetime.now()) # Input de data de fim
    
    st.divider() # Linha divisória
    
    # Botão de Processar
    if st.button("🚀 Processar Conversas", type="primary"): # Botão para iniciar o processamento das conversas
        if not ids_sel: # Verifica se alguma tag foi selecionada
            st.warning("Selecione uma tag.") # Exibe aviso se nenhuma tag for selecionada
        else: # Se tags foram selecionadas, inicia o processamento
            with st.spinner("Buscando conversas..."): # Mostra spinner enquanto busca conversas
                lista_conv = buscar_conversas(ids_sel, d1, d2) # Busca as conversas com base nas tags e datas selecionadas
            
            if not lista_conv: # Verifica se alguma conversa foi encontrada
                st.warning("Nada encontrado.") # Exibe aviso se nenhuma conversa foi encontrada
            else: # Se conversas foram encontradas, inicia a análise
                st.info(f"Analisando {len(lista_conv)} tickets...") # Informa o número de tickets a serem analisados
                progresso = st.progress(0) # Barra de progresso para mostrar o andamento da análise
                dados_temp = [] # Lista temporária para armazenar os dados analisados
                
                # Container temporário para mostrar progresso visual
                display_container = st.container()
                
                for i, conv in enumerate(lista_conv): # Itera sobre as conversas encontradas
                    c_id = conv['id'] # Obtém o ID da conversa
                    progresso.progress((i+1)/len(lista_conv)) # Atualiza a barra de progresso
                    
                    texto_ticket = ler_conversa_completa(c_id) # Lê a conversa completa do ticket
                    # Cria o prompt para a análise da IA
                    prompt = f""" 
                    Você é um analisador de conversas de suporte premium. Analise a seguinte conversa de suporte completa:
                    {texto_ticket}
                    
                    Responda de forma resumida e objetiva aos seguintes pontos:
                    1. **Motivo do contato**: (O que o cliente queria?)
                    2. **Quantos problemas relatados**: (Qual a dor?)
                    3. **Principais dúvidas ou reclamações**:
                    4. Ação do agente:
                    5. **Finalizada por falta de contato?** (Sim/Não)
                    6. **Potencial para automação por bot?** (0 a 10 e o motivo)
                    7. **Oportunidade de melhoria:** (Se houver)
                    """
                    # Chama o modelo Gemini de forma segura
                    resposta_texto = chamar_gemini_seguro(prompt)
                    campos_extraidos = processar_resposta_texto(resposta_texto) # Processa a resposta para extrair os campos relevantes
                    
                    linha = { # Cria uma linha de dados com as informações extraídas
                        "ID": c_id, # ID do ticket
                        "Data": datetime.fromtimestamp(conv['created_at']).strftime('%d/%m/%Y'), # Data de criação formatada
                        "Link": f"https://app.intercom.com/a/inbox/{INTERCOM_APP_ID}/inbox/conversation/{c_id}", # Link para o ticket no Intercom
                        **campos_extraidos, # Adiciona os campos extraídos da análise
                        "Análise Completa": resposta_texto # Texto completo da análise feita pela IA
                    }
                    dados_temp.append(linha) # Adiciona a linha de dados à lista temporária
                    
                    with display_container.expander(f"Analisando Ticket #{c_id}...", expanded=True): # Mostra o progresso da análise no container
                        st.markdown(resposta_texto) # Exibe o texto da análise
                    
                    time.sleep(0.5) # Pequena pausa para evitar sobrecarga na interface
                # Após processar todas as conversas, armazena os resultados na variável de sessão
                st.session_state['df_resultado'] = pd.DataFrame(dados_temp)
                st.rerun() # Recarrega a página para mostrar os resultados

# --- 5. EXIBIÇÃO DOS RESULTADOS ---
if st.session_state['df_resultado'] is not None: # Se houver resultados para exibir
    df = st.session_state['df_resultado'] # Obtém o DataFrame de resultados da variável de sessão

    # --- TOPO: DOWNLOAD ---
    with top_container: # Container no topo da página para download
        st.success("✅ Análise Finalizada!") # Mensagem de sucesso
        buffer = io.BytesIO() # Cria um buffer em memória para o arquivo Excel
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer: # Usa ExcelWriter para escrever o DataFrame no buffer
            df.to_excel(writer, index=False, sheet_name='Analise') # Escreve o DataFrame na planilha 'Analise'
        
        st.download_button( # Botão de download para o arquivo Excel
            label="📥 BAIXAR RELATÓRIO EXCEL (.xlsx)",
            data=buffer, # Dados do arquivo a ser baixado
            file_name=f"analise_suporte_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", # Nome do arquivo com timestamp
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", # Tipo MIME para arquivo Excel
            use_container_width=True # Usa a largura do container para o botão
        )
        st.divider() # Linha divisória

   # --- ANÁLISE RESUMIDA ---
    st.subheader("📈 Análise de Oportunidades")
    df_automacao_alta = df[df['Nota Automação'] >= 7] # Filtra os tickets com alta automação (nota 7 ou mais)
    col1, col2 = st.columns([1, 2]) # Cria duas colunas para exibir métricas e gráficos
    with col1: # Primeira coluna para métricas
        st.metric("Total Analisado", len(df)) # Mostra o total de tickets analisados
        st.metric("Alta Automação (Nota 7+)", len(df_automacao_alta)) # Mostra o total de tickets com alta automação
    with col2: # Segunda coluna para gráficos
        if not df_automacao_alta.empty: # Verifica se há dados suficientes para o gráfico
            st.markdown("#### Principais Motivos (Bot)") # Título do gráfico
            st.bar_chart(df_automacao_alta['Motivo'].value_counts().head(10)) # Gráfico de barras dos principais motivos para alta automação
        else:
            st.info("Sem dados suficientes para gráfico.") # Mensagem caso não haja dados suficientes

    st.divider() # Linha divisória

    # --- DETALHES DAS CONVERSAS ---
    st.subheader("📝 Detalhes das Conversas")
    
    # Itera sobre cada linha do DataFrame para criar expanders com detalhes
    for index, row in df.iterrows():
        # Define o ícone com base na nota de automação
        nota = row.get('Nota Automação', 0)
        icone = "🤖" if nota >= 7 else "👤" 
        
        with st.expander(f"{icone} Ticket #{row['ID']} - {row['Data']} (Nota Bot: {nota})"): # Expander para cada ticket
            st.markdown(row['Análise Completa']) # Exibe o texto completo da análise
            st.markdown(f"[🔗 Abrir no Intercom]({row['Link']})") 

    # Botão para nova análise
    if st.button("🔄 Nova Análise"):
        st.session_state['df_resultado'] = None # Reseta os resultados
        st.rerun() # Recarrega a página

elif not st.session_state['df_resultado']: # Se não houver resultados e nenhuma análise foi feita
    st.info("👈 Selecione as tags e datas na barra lateral para começar.") 
