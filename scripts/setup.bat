@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   CONFIGURACAO AUTOMATICA - MAPA DA SEGURANCA DF
echo   Ambiente 100%% Python (Windows)
echo ========================================================
echo.

:: 1. Verificar Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERRO] Python nao foi encontrado no PATH do Windows!
    echo Por favor, instale o Python 3.10 ou superior marcando a opcao "Add Python to PATH".
    echo Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [OK] Python detectado:
python --version
echo.

:: 2. Criar e configurar Ambiente Virtual (venv)
cd /d "%~dp0\.."
if not exist "venv" (
    echo [*] Criando ambiente virtual Python (venv)...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao criar o venv.
        pause
        exit /b 1
    )
    echo [OK] Ambiente virtual criado com sucesso.
) else (
    echo [INFO] Ambiente virtual 'venv' ja existe.
)

echo [*] Ativando venv e instalando dependencias Python...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [AVISO] Houve algum aviso na instalacao do pip.
) else (
    echo [OK] Dependencias instaladas com sucesso!
)
echo.

:: 3. Gerar dataset inicial se necessario
if not exist "data\ocorrencias_df.csv" (
    echo [*] Gerando base de dados de demonstracao do DF...
    python -c "from api.services.data_ingestion import gerar_dados_amostra; gerar_dados_amostra()"
    echo [OK] Base de dados inicial gerada.
)

echo.
echo ========================================================
echo   CONFIGURACAO CONCLUIDA COM SUCESSO!
echo ========================================================
echo Para iniciar o sistema completo:
echo   Execute o arquivo run.bat ou digite 'python run.py'
echo ========================================================
pause
