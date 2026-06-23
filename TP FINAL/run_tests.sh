#!/bin/bash
# Executa todos os testes unitários e de integração localmente (sem Docker).
# Requer: pip install fastapi uvicorn sqlalchemy passlib python-jose httpx pytest pytest-asyncio websockets redis pydantic pydantic-settings psycopg2-binary asyncpg

set -e

echo "=== Instalando dependências (auth-service) ==="
pip install -q -r auth-service/requirements.txt

echo "=== Instalando dependências (chat-service) ==="
pip install -q -r chat-service/requirements.txt

echo ""
echo "=== Testes Unitários – Auth Service ==="
cd auth-service
python -m pytest tests/test_unit.py -v
cd ..

echo ""
echo "=== Testes de Integração – Auth Service ==="
cd auth-service
python -m pytest tests/test_integration.py -v
cd ..

echo ""
echo "=== Testes Unitários – Chat Service ==="
cd chat-service
python -m pytest tests/test_unit.py -v
cd ..

echo ""
echo "=== Testes de Integração – Chat Service ==="
cd chat-service
python -m pytest tests/test_integration.py -v
cd ..

echo ""
echo "=== Todos os testes concluídos! ==="
