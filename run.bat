@echo off
cd /d "%~dp0"

echo ========================================================
echo   MAPA DA SEGURANCA DO DISTRITO FEDERAL
echo   Ambiente 100%% Python (Streamlit + FastAPI)
echo ========================================================
echo.

if not exist "venv" (
    echo [*] Ambiente virtual nao encontrado. Executando configuracao inicial...
    call scripts\setup.bat
    if %errorlevel% neq 0 exit /b 1
)

call venv\Scripts\activate.bat

echo Escolha como deseja iniciar:
echo [1] Iniciar Sistema Completo (API REST + Streamlit)
echo [2] Iniciar Apenas o Web App (Streamlit)
echo [3] Iniciar Apenas o Backend (API REST)
echo [0] Sair
echo.
set /p opcao="Digite a opcao desejada [1]: "

if "%opcao%"=="" set opcao=1
if "%opcao%"=="1" python run.py todos
if "%opcao%"=="2" python run.py app
if "%opcao%"=="3" python run.py api
if "%opcao%"=="0" exit /b 0

pause

