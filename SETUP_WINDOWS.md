# 🪟 Guia de Configuração de Ambiente no Windows

Este guia foi elaborado para que os colegas de equipe configurem e executem o **Mapa da Segurança DF** no Windows com rapidez e sem problemas de ambiente.

> [!NOTE]
> O projeto é **100% Python**. Não é necessário instalar Node.js, npm ou compiladores extras.

---

## 1. Único Pré-requisito: Python 3.10 ou Superior

1. Baixe o instalador oficial do Python em: [python.org/downloads](https://www.python.org/downloads/)
2. ⚠️ **ATENÇÃO (Passo Crucial)**: Na primeira tela da instalação, marque a caixa:
   - ☑️ **"Add python.exe to PATH"** (Adicionar Python às variáveis de ambiente).
3. Conclua a instalação padrão.

---

## 2. Inicialização em Um Clique (Recomendado)

1. Abra a pasta do projeto no Windows Explorer.
2. Dê um duplo clique no arquivo:
   ```cmd
   run.bat
   ```
3. O script fará tudo de forma automática:
   - Criará o ambiente virtual `venv` caso ainda não exista.
   - Instalará todas as bibliotecas necessárias do `requirements.txt`.
   - Inicializará a base de dados de demonstração do DF.
   - Abrirá tanto o **Web App Streamlit** quanto a **API REST (FastAPI)**.

---

## 3. URLs do Sistema

Após a inicialização:
- **Painel Web (Streamlit)**: [http://localhost:8501](http://localhost:8501)
- **Documentação Swagger da API**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 4. Execução Manual pelo Prompt de Comando (CMD)

Se preferir rodar manualmente comando por comando:

```cmd
:: 1. Criar o ambiente virtual (apenas na primeira vez)
python -m venv venv

:: 2. Ativar o ambiente virtual
venv\Scripts\activate.bat

:: 3. Instalar as dependências
pip install -r requirements.txt

:: 4. Iniciar todo o sistema (API + Streamlit)
python run.py

:: (Opcional) Se quiser rodar apenas o Streamlit:
:: python run.py app

:: (Opcional) Se quiser rodar apenas a API:
:: python run.py api
```

---

## 5. Banco de Dados Real (Opcional): PostgreSQL + PostGIS via Docker

Por padrão, o sistema roda com dados de demonstração. Para usar os **dados reais da SSP-DF** com o mapa coropleto, é preciso subir o banco:

1. **Instale o Docker Desktop**: [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
   (após instalar, reinicie o computador e abra o Docker Desktop uma vez).

2. **Suba o banco** (na pasta do projeto):
   ```cmd
   docker compose up -d
   ```
   Na primeira execução as tabelas são criadas automaticamente.

3. **Carregue os dados reais**:
   ```cmd
   venv\Scripts\activate.bat
   python -m db.load_csv
   python -m db.smoke_test
   ```

4. **Reinicie a API** (`python run.py api`) — o painel passará a exibir o mapa coropleto por RA e o filtro de Eixo Indicador.

> [!TIP]
> Sem o Docker/banco no ar, tudo continua funcionando no modo fallback (dados simulados). O banco é necessário apenas para os dados reais.

---

## 6. Resolução de Problemas Comuns

---

### Erro: "A execução de scripts foi desabilitada neste sistema" (PowerShell)
Se estiver utilizando o PowerShell e o comando de ativação do venv for bloqueado:
1. Abra o PowerShell como Administrador e execute:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```
2. Digite `S` (Sim) e confirme.

### Erro: "python não é reconhecido como um comando interno ou externo"
O Python não foi marcado com a opção "Add to PATH" durante a instalação.
- Reabra o instalador do Python, selecione **Modify** e marque a caixa **Add Python to PATH**.

### Porta já em uso (8000 ou 8501)
Se outra aplicação no computador já estiver usando essas portas, você pode especificar portas alternativas:
```cmd
python run.py --porta-api 8080 --porta-app 8502
```
