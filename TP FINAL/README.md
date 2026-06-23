# Nexus Chat — Trabalho Final de Sistemas Distribuídos

Sistema de chat em tempo real com arquitetura de microsserviços.

**Disciplina:** Sistemas Distribuídos &nbsp;|&nbsp; **Professora:** Michelle Hanne &nbsp;|&nbsp; **CEFET-MG 2026/1**  
**Aluna:** Ester Morais Neves

---

## Sobre o projeto

O **Nexus Chat** é uma plataforma de comunicação em tempo real construída com arquitetura de microsserviços. Usuários podem conversar em canais públicos (1:N) e em mensagens diretas (1:1), com entrega instantânea das mensagens via WebSockets.

## Arquitetura

```
Browser → Nginx (porta 80) → Auth Service  (FastAPI · JWT · bcrypt)
                           → Chat Service  (FastAPI · WebSocket · Redis Pub/Sub)  ×2 réplicas
                                    ↕
                             PostgreSQL (users · messages · rooms)
                             Redis      (sincronização entre réplicas)
```

Todos os componentes rodam em containers Docker orquestrados pelo Docker Compose. O Nginx funciona como reverse proxy e balanceador de carga entre as duas réplicas do Chat Service.

## Stack técnica

| Camada | Tecnologia |
|---|---|
| Frontend | HTML5 · CSS3 · JavaScript puro |
| Backend | Python · FastAPI |
| Banco de dados | PostgreSQL 15 |
| Mensageria | Redis 7 (Pub/Sub) |
| Autenticação | JWT (HS256) + bcrypt |
| Infraestrutura | Docker Compose · Nginx |
| Testes | pytest (33 testes — unitários + integração) |

## Funcionalidades

- Cadastro e login com autenticação JWT
- Canais públicos com criação dinâmica pelo usuário
- Mensagens diretas (1:1) entre usuários
- Histórico de mensagens persistido no banco (novos usuários veem conversas anteriores)
- Exclusão de conta (soft delete via `DELETE /users/me`)
- Reconexão automática do WebSocket após queda
- Badge de mensagens não lidas por canal/DM
- Escalabilidade horizontal via Redis Pub/Sub

## Como rodar

Pré-requisito: Docker Desktop instalado e rodando.

```bash
# Na pasta TP FINAL
docker compose up --scale chat-service=2
```

Acesse em: `http://localhost`

## Testes

```bash
# Auth Service
cd auth-service
pip install -r requirements.txt
pytest tests/ -v

# Chat Service
cd chat-service
pip install -r requirements.txt
pytest tests/ -v
```

Ou use os scripts prontos:
- **Windows:** `run_tests.ps1`
- **Linux/Mac:** `run_tests.sh`

## Estrutura de arquivos

```
TP FINAL/
├── auth-service/         # Microsserviço de autenticação
│   ├── main.py
│   ├── requirements.txt
│   └── tests/
├── chat-service/         # Microsserviço de chat
│   ├── main.py
│   ├── requirements.txt
│   └── tests/
├── frontend/             # Interface web (HTML/CSS/JS)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── load-test/            # Script de teste de carga
├── docker-compose.yml
├── nginx.conf
├── relatorio.html        # Relatório do trabalho
└── apresentacao.html     # Slides de apresentação
```
