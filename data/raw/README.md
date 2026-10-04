# Pasta para arquivos brutos da SSP-DF (Raw Data)

Coloque aqui as planilhas `.xls`/`.xlsx` do Balanço Criminal baixadas do portal
da SSP-DF, uma por Região Administrativa e ano. O nome do arquivo segue o
padrão do portal:

- `00_DISTRITO_FEDERAL-2022_2022.xlsx` (agregado do DF, tem `OCORRENCIA`/`VITIMA`)
- `09_CEILANDIA_2024.xlsx`
- `03_TAGUATINGA-68_2020.xlsx`

Depois de baixar, consolide tudo num único CSV com:

```bash
python -c "from api.services.ingest_crimemap import consolidar; from pathlib import Path; consolidar(Path('data/raw'), Path('api/services/output/crimemap_consolidadov2.csv'))"
```

Ou pela aba **⚙️ Consolidação de Dados (ETL)** no Streamlit.

O CSV consolidado alimenta tanto a carga do banco (`python -m db.load_csv`)
quanto o modo fallback do painel. O consolidado já versionado
(`api/services/output/crimemap_consolidadov2.csv`) foi gerado a partir dos
arquivos desta pasta.

## Atenção: o ano dentro do arquivo manda

Alguns arquivos do portal vêm com o ano no **nome** diferente do ano da
**planilha interna** (ex.: `09_CEILANDIA_2024.xlsx` contém a aba
`PPV (mensal)2022`). O parser usa sempre o ano do cabeçalho interno, não o do
nome do arquivo — é o que a planilha declara que conta. Como consequência,
nem todo ano tem cobertura das 33 RAs: o que falta nos arquivos por RA
aparece apenas no agregado do Distrito Federal.
