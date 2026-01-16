# Análise de Conversas com IA 💎

Este projeto é uma ferramenta de inteligência de dados desenvolvida em **Python** e **Streamlit**. O objetivo é conectar o **Intercom** à IA do Google (**Gemini**) para ler, interpretar e categorizar conversas de suporte automaticamente, gerando *insights* sobre motivos de contato e oportunidades de automação.

## 🚀 Funcionalidades

* **Filtros Avançados:** Seleção de conversas por **Tags** (importadas do Intercom) e intervalo de datas.
* **Análise com IA (Gemini):** Cada conversa é lida por um modelo de IA que extrai automaticamente:
    * Motivo do contato.
    * Dores e dúvidas principais do cliente.
    * Ação realizada pelo agente.
    * Detecção de encerramento por falta de contato.
* **Score de Automação:** A IA atribui uma nota (0 a 10) sobre o potencial daquela conversa ter sido resolvida por um bot.
* **Dashboard Visual:** Gráficos que destacam os principais motivos de contacto em tickets com alto potencial de automação.
* **Exportação:** Gera um relatório completo em **Excel (.xlsx)** com todas as análises.

## 🛠️ Instalação e Requisitos

Este projeto requer **Python** e as bibliotecas listadas no `requirements.txt`.

1.  **Clonar o repositório:**
    ```bash
    git clone https://teu-repositorio/analise-conversas.git
    cd analise-conversas
    ```

2.  **Instalar dependências:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Arquivo de Tags:**
    O sistema precisa de um arquivo chamado `tags_intercom.xlsx` na raiz do projeto para mapear os nomes das tags para os seus IDs do Intercom.

## 🔐 Configuração (Secrets)

As credenciais de acesso devem ser configuradas no ficheiro `.streamlit/secrets.toml`.

```toml
# .streamlit/secrets.toml

INTERCOM_TOKEN = "teu_token_intercom"
INTERCOM_APP_ID = "teu_app_id"
GEMINI_API_KEY = "tua_chave_api_google_gemini"
PASSWORD = "senha_para_acessar_o_painel"
