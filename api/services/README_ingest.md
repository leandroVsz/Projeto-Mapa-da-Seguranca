# Como usar o `ingest_crimemap.py`

## 1. Baixe os arquivos manualmente

Baixe os `.xls`/`.xlsx` do portal da SSP-DF (uma RA por vez, ou o
consolidado do Distrito Federal) e coloque todos numa pasta, por
exemplo `raw_data/`. Pode misturar `.xls` e `.xlsx` na mesma pasta,
e pode ter mais de uma aba (ano) por arquivo — o script lida com isso
automaticamente.

## 2. Prepare o ambiente (Linux)

```bash
python3 -m venv venv
source venv/bin/activate
pip install pandas xlrd openpyxl
```

- `xlrd` é necessário para ler os arquivos `.xls` antigos (Excel 97-2003).
- `openpyxl` é necessário para os arquivos `.xlsx` mais recentes.

## 3. Rode o script

```bash
python3 ingest_crimemap.py --input raw_data/ --output output/crimemap_consolidado.csv
```

Ele imprime no terminal quantas abas foram processadas por arquivo, um
resumo final (regiões, anos, total de linhas) e qualquer aviso de aba
que não pôde ser lida (por exemplo, se algum arquivo vier com um
layout diferente do esperado).

## 4. O que o CSV consolidado contém

Uma linha por (região administrativa, ano, tipo de crime), no formato
"largo" (uma coluna por mês):

| coluna | descrição |
|---|---|
| `regiao_administrativa` | nome da RA extraído do próprio cabeçalho da planilha (ou "Distrito Federal" para o agregado) |
| `codigo_ra_arquivo` | código numérico extraído do **nome do arquivo** (prefixo, ex: `9_ceilandia...` → `09`) |
| `ano` | ano da aba/planilha |
| `eixo_indicador` | categoria macro (C.V.L.I., C.C.P., Outros Crimes, Produtividade Policial) |
| `tipo_registro` | `OCORRENCIA` ou `VITIMA` — só existe distinção no arquivo do DF; nos arquivos por RA vem sempre `OCORRENCIA` |
| `natureza` | tipo específico do crime (ex: HOMICÍDIO, ROUBO DE VEÍCULO) |
| `total_ano`, `jan`...`dez` | contagens |
| `arquivo_origem`, `aba_origem` | rastreabilidade — de qual arquivo/aba veio cada linha |

## 5. Duas coisas para ficar de olho

- **Acentuação inconsistente na fonte**: reparei que a própria SSP-DF
  escreve "RA I - BRASILIA" sem acento em alguns arquivos e
  "CEILÂNDIA" com acento em outros — o script extrai o nome
  exatamente como está na planilha. **Isso já é resolvido na carga do
  banco** (`db/load_csv.py`), que normaliza grafias, remove sufixos de
  re-download (ex: "Arniqueira (4)") e unifica RAs renomeadas
  ("Varjão do Torto" → "Varjão") via dicionário de apelidos.
- **Se o portal mudar o layout**: o script foi desenhado para ser
  resiliente a várias variações que já vi nos seus 6 arquivos de
  exemplo (posição do cabeçalho, coluna extra, ausência de linhas de
  subtotal). Se algum arquivo novo vier com uma célula-âncora
  diferente de `"EIXOS INDICADORES"` ou `"NATUREZA"`, o script vai
  pular a aba com um aviso em vez de gerar dados errados — é assim
  que você vai perceber que precisa ajustar o parser.

## Resultado nos seus 6 arquivos de exemplo

```
✔ Consolidado salvo em: output/crimemap_consolidado.csv
  Linhas: 372
  Regiões administrativas: 6
  Anos: [2014, 2015, 2016, 2017, 2018, 2026]
```

Validei também que, em todas as 372 linhas, a soma dos 12 meses bate
exatamente com o total anual declarado na planilha — bom indício de
que a extração está correta mesmo com as variações de layout entre
anos e arquivos.

> **Nota**: no CSV completo (7.020 linhas, todas as RAs), 65 linhas dos
> anos 2014/2016/2017 têm `total_ano` ≠ soma dos meses — inconsistência
> da própria fonte. A carga no banco usa os valores mensais como
> verdade granular.

## 6. Do CSV consolidado para o banco PostgreSQL

Depois de gerar o CSV consolidado, carregue-o no banco:

```bash
docker compose up -d          # sobe PostgreSQL + PostGIS
cp .env.example .env          # configuração da conexão
python -m db.load_csv         # carga: dimensões + fato + contornos
python -m db.smoke_test       # valida se banco × CSV batem
```

O que a carga faz:

1. **Normaliza regiões** (acentos, sufixos "(4)", RAs renomeadas) → 34 RAs limpas;
2. **Limpa eixos e naturezas** (remove "1. ", espaços duplicados, "*" de notas);
3. **Despivota** as colunas jan..dez em linhas mensais (~84 mil registros no fato);
4. **Baixa os contornos** das RAs (GeoJSON do GeoInfo-DF, com cache em `data/geo/`)
   e grava `contorno` (polígono) + `centroide` no PostGIS;
5. **Upsert idempotente** — pode rodar novamente a cada novo CSV consolidado.
