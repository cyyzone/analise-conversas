import requests # O meu "motoboy" que busca e leva dados na internet.
import google.generativeai as genai # O cérebro da operação (IA do Google).
import time # O relógio, essencial pra dar pausas dramáticas (e não travar a API).
import streamlit as st # O palco onde meu show acontece (o site).
import pandas as pd # O Excel superpoderoso do Python.
from datetime import datetime, timezone, timedelta, time as dt_time # Minha agenda completa.
import re # A "lupa" (Regex) pra encontrar padrões no meio do texto.
import io # Uma "pasta virtual" pra criar arquivos na memória sem salvar no PC.

# --- 1. CONFIGURAÇÕES ---
# Defino o nome da aba e o ícone de diamante, porque esse painel vale ouro! 💎
st.set_page_config(page_title="Analise de conversas", page_icon="💎", layout="wide") 

# --- 🔐 O SEGURANÇA DA BALADA (Login) ---
def check_password(): # Comparo o que digitaram com a senha que guardei no cofre (secrets).
    """Retorna True se o usuário tiver a senha correta."""

    def password_entered(): 
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
        type="password", # Esconde as letras com bolinhas •••
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

# --- 2. MINHAS ASSISTENTES (Funções Auxiliares) ---

def fazer_requisicao_segura(method, url, json=None, params=None, max_retries=5): # Essa é a minha diplomata. Ela fala com o Intercom com todo cuidado. Se o Intercom disser 'tô ocupado' (Rate Limit), ela espera pacientemente.
    headers = { #   Cabeçalhos HTTP - API
        "Authorization": f"Bearer {INTERCOM_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    for attempt in range(max_retries): # Tenta algumas vezes, porque sou brasileira e não desisto.
        try: # Dependendo do método, faz a requisição apropriada
            if method == "POST": # POST request
                resp = requests.post(url, json=json, headers=headers) # Faz requisição POST
            else: # GET request
                resp = requests.get(url, params=params, headers=headers) # Faz requisição GET
            
            if resp.status_code == 200: # Se a resposta for bem-sucedida, retorna o JSON
                return resp.json() # Retorna o JSON da resposta
            elif resp.status_code == 429: # Eita, o Intercom pediu um tempo. Rate Limit atingido.
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

def chamar_gemini_seguro(prompt):# Função para chamar o modelo Gemini com tratamento de erro. Minha conversa com a IA. Às vezes ela 'alucina' ou falha, então eu insisto.
    for attempt in range(3): # # Tento 3 vezes conversar com a gata.
        try: # Tenta gerar o conteúdo com o modelo
            response = model.generate_content(prompt) # Gera o conteúdo usando o modelo Gemini
            return response.text # Retorna o texto que a IA  gerou.
        except: # Em caso de exceção, aguarda um tempo exponencial antes de tentar novamente
            time.sleep(2 ** (attempt + 1)) # Espero exponencialmente (2s, 4s, 8s...) pra não ser chata.   
    return "Falha na análise da IA." # Desisto.

def extrair_nota_automacao(texto_automacao): # Função para extrair a nota de automação do texto
    match = re.search(r'\b(10|[0-9])\b', str(texto_automacao)) # Procura por um número entre 0 e 10 no texto 
    if match: return int(match.group(1)) # Retorna a nota encontrada
    return 0 # Retorna 0 se nenhuma nota for encontrada

#A GRANDE MÁGICA! 
#A IA me devolve um textão. Aqui eu uso 'Regex' (minha lupa) pra picotar esse texto e guardar cada informação na sua caixinha certa (Motivo, Problema, Ação...).
def processar_resposta_texto(texto): # Função para processar a resposta de texto da IA e extrair campos específicos
    dados = { # Dicionário para armazenar os dados extraídos
        "Motivo": "Não identificado", "Qtd Problemas": "", "Dúvidas": "", # Campos padrão
        "Ação": "", "Falta Contato": "", "Automação Texto": "", 
        "Nota Automação": 0, "Melhoria": ""
    }
    # Esses códigos estranhos são as "regras" pra achar onde começa e termina cada resposta.
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
        if match: # Limpo a sujeira (**negrito**, crases) pra ficar bonito na tabela.
            dados[chave] = match.group(1).strip().replace("**", "").replace("`", "") # Limpa o texto extraído
    
    if dados["Automação Texto"]: # Extrai a nota de automação se o texto estiver presente
        dados["Nota Automação"] = extrair_nota_automacao(dados["Automação Texto"]) # Extrai a nota de automação do texto
    return dados # Retorna o dicionário com os dados extraídos

# --- 3. FUNÇÕES PRINCIPAIS ---
@st.cache_data(show_spinner=False)
def carregar_motivos():
    try:
        # Lê o arquivo Excel que você enviou
        df = pd.read_excel("Motivos de contato.xlsx")
        # Pega a coluna e transforma numa lista do Python
        motivos = df["MOTIVO DE CONTATO (ATRIBUTO)"].dropna().astype(str).tolist()
        return ["Selecione..."] + motivos
    except:
        return ["Selecione...", "Erro ao carregar a planilha"]

def buscar_conversas(tipo, motivo, motivo_2, d_inicio, d_fim):
    url = "https://api.intercom.io/conversations/search"
    ts_i = int(datetime.combine(d_inicio, dt_time.min).replace(tzinfo=timezone.utc).timestamp())
    ts_f = int(datetime.combine(d_fim, dt_time.max).replace(tzinfo=timezone.utc).timestamp())
    
    # 1. Pedimos para a API buscar APENAS pelas datas (isso funciona sempre)
    payload = {
        "query": {
            "operator": "AND",
            "value": [
                {"field": "created_at", "operator": ">", "value": ts_i},
                {"field": "created_at", "operator": "<", "value": ts_f}
            ]
        },
        "pagination": {"per_page": 50},
        "sort": {"field": "created_at", "order": "desc"}
    }
    
    todas_conversas = []
    while True:
        data = fazer_requisicao_segura("POST", url, json=payload)
        if not data: break
        todas_conversas.extend(data.get('conversations', []))
        pag = data.get('pages', {})
        if pag.get('next'):
            payload['pagination']['starting_after'] = pag['next']['starting_after']
        else: break
            
    # 2. Agora o Python faz o filtro fino com os atributos!
    conversas_filtradas = []
    for conv in todas_conversas:
        atributos = conv.get("custom_attributes", {})
        
        # Pega os valores que vieram no ticket
        tipo_conv = atributos.get("Tipo de Atendimento", "Vazio")
        motivo_conv = atributos.get("Motivo de Contato", "Vazio")
        motivo2_conv = atributos.get("Motivo 2 (Se houver)", "Vazio")
        
        # Regra A: O Tipo de Atendimento tem que bater
        if tipo_conv != tipo:
            continue
            
        # Regra B: Se você escolheu um Motivo 1, ele tem que bater
        if motivo and motivo != "Selecione...":
            if motivo_conv != motivo:
                continue
                
        # Regra C: Se você escolheu um Motivo 2, ele tem que bater
        if motivo_2 and motivo_2 != "Selecione...":
            if motivo2_conv != motivo_2:
                continue
                
        # Se passou por todas as regras, é a conversa certa!
        conversas_filtradas.append(conv)
        
    return conversas_filtradas
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

with st.sidebar:
    st.header("Filtros")
    
    # Opções principais (atenção para deixar as maiúsculas iguais ao Intercom)
    opcoes_tipo = [
        "Selecione...",
        "Dúvida",
        "Ação manual realizada em N1",
        "Chamado (N2/CSM/IMP/Fin)",
        "Expansão"
    ]
    
    tipo_selecionado = st.selectbox("Tipo de Atendimento:", opcoes_tipo)
    
    # Criamos as variáveis vazias primeiro
    motivo_contato = None
    motivo_2 = None
    
    # Só mostra os próximos campos se um tipo for escolhido
    if tipo_selecionado != "Selecione...":
        
        # Puxa os 333 motivos direto do Excel!
        lista_motivos = carregar_motivos()
        
        motivo_contato = st.selectbox("Motivo de Contato:", lista_motivos)
        motivo_2 = st.selectbox("Motivo 2 (Se houver):", lista_motivos)

    st.divider()
    d1 = st.date_input("Início", datetime.now()-timedelta(days=7))
    d2 = st.date_input("Fim", datetime.now())
    
    st.divider()
    
    # Botão de Processar
    if st.button("🚀 Processar Conversas", type="primary"):
        if tipo_selecionado == "Selecione...":
            st.warning("Selecione um Tipo de Atendimento para começar.")
        else:
            with st.spinner("Buscando conversas..."):
                # A função de busca que atualizamos na mensagem anterior
                lista_conv = buscar_conversas(tipo_selecionado, motivo_contato, motivo_2, d1, d2)
            
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
                    
                    # --- NOVO CÓDIGO AQUI: Capturando os atributos ---
                    # Pegamos o dicionário de atributos personalizados da conversa
                    atributos = conv.get("custom_attributes", {})
                    
                    # Extraímos os valores exatos que você precisa
                    tipo_atendimento = atributos.get("Tipo de Atendimento", "Vazio")
                    col_expansao = atributos.get("COL_EXPANSAO", "Vazio")
                    motivo_contato = atributos.get("Motivo de Contato", "Vazio")
                    motivo_2 = atributos.get("Motivo 2 (Se houver)", "Vazio")
                    status_atendimento = atributos.get("Status do atendimento", "Vazio")
                    # --------------------------------------------------
                    
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
                        
                        # --- NOVO CÓDIGO AQUI: Adicionando na tabela ---
                        "Tipo de Atendimento": tipo_atendimento, 
                        "COL_EXPANSAO": col_expansao,           
                        "Motivo de Contato": motivo_contato,    
                        "Motivo 2 (Se houver)": motivo_2,       
                        "Status do atendimento": status_atendimento, 
                        # --------------------------------------------------
                        
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
