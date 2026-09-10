# Pasta para arquivos brutos da SSP-DF (Raw Data)

Coloque aqui os arquivos anuais baixados por Região Administrativa / Cidade, por exemplo:
- `ceilandia_2021.csv`
- `ceilandia_2022.csv`
- `ceilandia_2023.csv`
- `taguatinga_2021.csv`
- `taguatinga_2022.csv`

Depois, acesse a aba **⚙️ Consolidação de Dados (ETL)** no Streamlit ou execute:
```bash
python -c "from backend.services.data_ingestion import consolidar_arquivos_por_cidade; consolidar_arquivos_por_cidade('backend/data/raw', 'backend/data/processed')"
```
Isso criará os arquivos unificados por cidade e o arquivo consolidado de todo o Distrito Federal!

