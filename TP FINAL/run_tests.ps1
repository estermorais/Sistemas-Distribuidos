# Executa todos os testes no Windows (PowerShell)
# Requer Python instalado

Write-Host "=== Instalando dependencias (auth-service) ===" -ForegroundColor Cyan
pip install -q -r auth-service/requirements.txt

Write-Host "=== Instalando dependencias (chat-service) ===" -ForegroundColor Cyan
pip install -q -r chat-service/requirements.txt

Write-Host "`n=== Testes Unitarios - Auth Service ===" -ForegroundColor Yellow
Set-Location auth-service
python -m pytest tests/test_unit.py -v
Set-Location ..

Write-Host "`n=== Testes de Integracao - Auth Service ===" -ForegroundColor Yellow
Set-Location auth-service
python -m pytest tests/test_integration.py -v
Set-Location ..

Write-Host "`n=== Testes Unitarios - Chat Service ===" -ForegroundColor Yellow
Set-Location chat-service
python -m pytest tests/test_unit.py -v
Set-Location ..

Write-Host "`n=== Testes de Integracao - Chat Service ===" -ForegroundColor Yellow
Set-Location chat-service
python -m pytest tests/test_integration.py -v
Set-Location ..

Write-Host "`n=== Todos os testes concluidos! ===" -ForegroundColor Green
