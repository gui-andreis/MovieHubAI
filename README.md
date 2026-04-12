# 🤖 MovieHub AI

Serviço de IA conversacional para o [MovieHub](https://github.com/gui-andreis/MovieHub), construído com LangGraph e FastAPI.

---

## 🧠 Tecnologias

- **Python 3.11** — linguagem principal
- **FastAPI** — API REST
- **LangGraph** — orquestração do agente com grafo de estado
- **LangChain + OpenAI** — LLM e tool calling (GPT-4o-mini)
- **Redis** — persistência do histórico de conversas por sessão
- **httpx** — cliente HTTP async para comunicação com o MovieHub
- **Docker + Docker Compose** — containerização
- **pytest** — testes unitários com mocks

---

## 🏗️ Arquitetura

O agente é um grafo de estado (LangGraph) com 4 nós:

memory → router → tool_executor → responder → END
↘ responder → END

- **memory** — carrega e persiste o histórico da sessão no Redis
- **router** — classifica a intenção do usuário via LLM
- **tool_executor** — executa tools relevantes para a intenção detectada
- **responder** — formata a resposta final com base nos dados retornados

---

## 🚀 Como rodar

### Pré-requisitos

- [Docker](https://www.docker.com/)
- [Docker Compose](https://docs.docker.com/compose/)
- MovieHub backend rodando ([instruções aqui](https://github.com/gui-andreis/MovieHub))
- Chave de API da OpenAI

### Passos

```bash
# Clone o repositório
git clone https://github.com/SEU_USUARIO/moviehub-ai.git
cd moviehub-ai

# Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env com sua OPENAI_API_KEY

# Suba o MovieHub primeiro
cd ../MovieHub
docker compose -f MovieHub/docker-compose.yml up --build

# Suba o serviço de IA
cd ../moviehub-ai
docker compose up --build
```

A API estará disponível em:
http://localhost:8000

O Swagger estará disponível em:
http://localhost:8000/docs

---

## 🔐 Autenticação

Endpoints que gerenciam favoritos e reviews requerem o JWT do MovieHub.

1. Faça login no MovieHub em `POST /api/auth/login`
2. Copie o token retornado
3. No Swagger do moviehub-ai, clique em **Authorize 🔒** e insira: `Bearer {seu_token}`

---

## 📋 Endpoint

### POST `/api/chat`

```json
{
  "message": "me recomenda um filme de ficção científica",
  "session_id": "usuario_123",
  "history": []
}
```

Resposta:

```json
{
  "reply": "Aqui estão algumas recomendações de ficção científica...",
  "session_id": "usuario_123",
  "intent": "get_recommendations"
}
```

### Intenções suportadas

| Intenção              | Exemplo                                  |
| --------------------- | ---------------------------------------- |
| `search_movies`       | "quero ver filmes de terror dos anos 90" |
| `get_recommendations` | "me recomenda algo bom pra assistir"     |
| `get_movie_details`   | "me fala mais sobre o Inception"         |
| `get_movie_reviews`   | "o que acharam do Interstellar?"         |
| `manage_favorites`    | "adiciona esse filme nos meus favoritos" |
| `manage_reviews`      | "quero dar nota 9 pro Oppenheimer"       |
| `list_my_favorites`   | "quais são meus favoritos?"              |
| `list_my_reviews`     | "quais filmes eu já avaliei?"            |
| `general_chat`        | "oi, tudo bem?"                          |

---

## 🧪 Testes

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Cobertura atual: **5 testes unitários** cobrindo os dois fluxos do grafo (com e sem tools), persistência de memória, e autenticação.

---

## 🗂️ Estrutura do Projeto

```bash
moviehub-ai/
├── app/
│   ├── main.py         # entrypoint FastAPI
│   └── config.py       # settings centralizadas (pydantic-settings)
├── agent/
│   ├── graph.py        # StateGraph compilado
│   ├── state.py        # AgentState
│   └── nodes/
│       ├── memory.py       # lê/escreve histórico no Redis
│       ├── router.py       # classifica intenção via LLM
│       ├── tool_executor.py # executa tools
│       └── responder.py    # formata resposta final
├── tools/
│   ├── moviehub_tools.py       # busca, detalhes, gêneros, reviews
│   ├── recommendation_tools.py # recomendações
│   └── authenticated_tools.py  # favoritos e reviews (requer JWT)
├── clients/
│   └── moviehub_client.py  # wrapper httpx para o MovieHub
├── memory/
│   └── redis_memory.py     # persistência por session_id
├── api/
│   ├── routes/chat.py      # POST /api/chat
│   └── schemas/chat.py     # ChatRequest / ChatResponse
└── tests/
├── conftest.py
└── test_graph.py
```

---

## 🛣️ Roadmap

### ✅ Concluído

- Agente LangGraph com roteamento por intenção
- Tools públicas — busca, detalhes, gêneros, recomendações, reviews
- Tools autenticadas — favoritos e reviews do usuário
- Memória de conversa persistida no Redis por sessão
- Tratamento de erros semântico (404, 409, 401, timeout, connection error)
- Testes unitários com mocks
- Docker Compose integrado ao MovieHub

### 🔧 Próximas melhorias

- [ ] Integração com TMDB para enriquecimento de dados
- [ ] Streaming de respostas (SSE)
- [ ] Frontend React
- [ ] Rate limiting
- [ ] Testes de integração

---

## 👨‍💻 Autor

Feito por **Guilherme Andreis**  
[LinkedIn](https://www.linkedin.com/in/guilherme-boeira-andreis) · [GitHub](https://github.com/gui-andreis)
