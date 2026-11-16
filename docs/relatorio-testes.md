# Seção 4 — Testes do Mapa da Segurança DF

> Documento de apoio para preenchimento do relatório do projeto.
> Os textos abaixo já estão no padrão das tabelas solicitadas e refletem a
> execução real da suíte em **06/11/2026**.

## 1. Identificação e ambiente de execução

| Item | Valor |
|---|---|
| Projeto | Mapa da Segurança — Distrito Federal (UCB, 8º semestre) |
| Versão avaliada | API 2.0.0 / branch `feature/testes` |
| Sistema operacional | Windows (Git Bash) |
| Python | 3.14.8 |
| Interface | Streamlit 1.65.0 |
| API | FastAPI 0.142.2 + Uvicorn 0.54.0 |
| Banco | PostgreSQL 18.6 com PostGIS (Neon), via SQLAlchemy 2.1.3 |
| Automação | pytest 9.1.1 + httpx 0.28.1 + `streamlit.testing.v1.AppTest` |
| Massa de dados | 77.904 registros mensais, 34 RAs, 25 naturezas, 4 eixos, 13 anos (2014–2026) |

**Como reproduzir**

```bash
pip install -r requirements.txt

# Suíte completa (151 verificações)
python -m pytest -v

# Por bloco do relatório
python -m pytest tests/test_funcional_api.py -v       # 4.1 — 46 verificações
python -m pytest tests/test_integracao_db.py -v       # 4.2.1 — 11 verificações
python -m pytest tests/test_integracao_servicos.py -v # 4.2.2 — 14 verificações
python -m pytest tests/test_usabilidade.py -v         # 4.3 — 31 verificações

# Cobertura de código
python -m pytest --cov --cov-report=term
```

Pré-requisitos dos testes de integração: `DATABASE_URL` válida no `.env`
(ou `TEST_DATABASE_URL`). Se o schema `auth` ainda não existir, a fixture da
suíte aplica `db/auth_schema.sql` de forma idempotente. Sem banco acessível,
apenas os testes marcados com `integracao_db` são pulados; os demais continuam
rodando no modo fallback (CSV).

**Resultado geral da execução**

```
151 passed, 1 warning in 189.42s
TOTAL: 78% de cobertura de linhas
```

---

## 2. Seção 4.1 — Teste funcional

Os testes tratam a aplicação como **caixa-preta**: usam apenas HTTP
(`TestClient` do FastAPI) ou os artefatos exportados, sem acessar detalhes
internos. A história do usuário (HU) foi numerada a partir das funcionalidades
descritas no README (consulta, mapa, filtros, tabela, detalhe, conta,
relatórios, exportação, modo offline e consistência dos indicadores).

| ID | Requisito/História | Cenário de teste | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|---|
| TF01 | HU01 — Consultar indicadores e status do sistema | Abrir o painel e consultar `GET /`, `/api/health` e `/api/stats` com o banco conectado | Respostas 200; totais positivos; quatro KPIs coerentes; banco reportado online | 200; 77.904 registros mensais; 34 RAs (33 com contorno); 1.253.139 ocorrências; RA líder **Ceilândia**; crime mais frequente **ROUBO A TRANSEUNTE** | Aprovado |
| TF02 | HU02 — Visualizar o mapa geoespacial | Consultar `/api/heatmap`, `/api/coropleto` e `/api/regioes` | Pontos dentro do DF; pesos entre 0,2 e 1,0; intensidade e top naturezas por RA | 33 pontos de calor válidos (máx. 1,0); 34 RAs no coropleto; top naturezas por RA presente | Aprovado |
| TF03 | HU03 — Filtrar ocorrências por RA, eixo, natureza e ano | Combinar RA + ano e filtrar por eixo; consultar RA inexistente | Total filtrado menor que o geral e coerente; filtro inexistente retorna 0 e “N/A” | Filtro `Ceilândia + 2026` reduz o total e mantém apenas 2026 na série; eixo filtra corretamente; RA inexistente → 0 / “N/A” | Aprovado |
| TF04 | HU04 — Consultar a tabela de ocorrências com busca | Listar com limite 20; buscar “Ceilândia”; buscar termo inexistente; limites 0 e 5001 | Lista dentro do limite e com schema correto; busca coerente; vazio quando não há resultado; 422 para limites inválidos | 20 linhas com `regiao_administrativa`, `natureza_crime`, `ano`, `mes` e `quantidade`; busca retorna somente RA/crime com o termo; 0 para “zzzzzzzz”; 422 nos limites inválidos | Aprovado |
| TF05 | HU05 — Abrir o painel de detalhe da RA no mapa | Consultar `/api/detalhe-regiao` para a RA líder do coropleto | Total do detalhe igual ao do coropleto; distribuições somam o total | **Ceilândia:** 110.192 ocorrências, igual ao coropleto; somas de natureza, mês e ano conferem; RA inexistente retorna estrutura vazia | Aprovado |
| TF06 | HU06 — Criar conta, autenticar e recuperar senha | Registrar; repetir e-mail; senha fraca; login errado e correto; `/eu`; logout; reset por token | Fluxo completo com mensagens seguras (sem revelar existência de conta) | Registro 200 com token; e-mail duplicado 409; senha fraca 422; login errado e inexistente com **mesma** mensagem 401; `/eu` 401 sem token e após logout; reset troca a senha e invalida a antiga | Aprovado |
| TF07 | HU07 — Salvar, listar e excluir relatórios na conta | Salvar; listar; repetir título; excluir; tentar excluir relatório de outro usuário | CRUD restrito ao dono; duplicidade e acesso indevido bloqueados | Salvar/listar 200; título repetido 409; exclusão 200 e segunda tentativa 404; usuário B recebe 404 ao tentar excluir relatório de A e continua vendo a própria lista vazia | Aprovado |
| TF08 | HU08 — Exportar análises e consolidar dados | Gerar CSV e PDF; conferir publicação das rotas de ETL no OpenAPI | CSV reimportável; PDF válido; endpoints publicados | CSV com BOM UTF-8 e separador `;` reaberto pelo pandas; PDF com 2 páginas e cabeçalho `%PDF`; `/api/consolidar` e `/api/carga-db` publicados | Aprovado |
| TF09 | HU09 — Usar o painel sem o backend | Desligar a API e consultar filtros, KPIs, mapa, tabela e detalhe pelo `ApiClient` | Mesmos dados/schema do modo online, lidos do CSV consolidado | `check_health` offline; 34 RAs, 25 naturezas, 13 anos; 1.253.139 ocorrências; 600 linhas na tabela; 13 pontos de calor; detalhe da RA líder disponível | Aprovado |
| TF10 | HU10 — Consistência entre indicadores e listagens | Comparar `/api/stats`, `/api/coropleto`, `/api/detalhe-regiao` e `/api/ocorrencias` com o mesmo filtro | Todas as agregações somam o mesmo total | Σ coropleto = 1.253.139 = Σ série anual; detalhe = coropleto da RA; listagem filtrada por RA+ano = total do `/api/stats` do mesmo filtro | Aprovado |

### Indicadores

| Indicador | Resultado |
|---|---|
| Quantidade total de testes | 10 cenários funcionais (46 verificações automatizadas) |
| Testes aprovados | 10 |
| Testes reprovados | 0 |
| Taxa de sucesso | 100% |

> Para a contagem geral do projeto: **151 verificações automatizadas**
> (46 funcionais + 11 de integração com banco + 14 de integração com
> serviços + 31 de usabilidade + 49 testes unitários já existentes),
> todas aprovadas.

### Defeitos encontrados e corrigidos nesta etapa

| ID | Defeito | Correção |
|---|---|---|
| D01 | O fallback de `/api/stats` lançava `TypeError` e o endpoint `POST /api/consolidar` não era registrado, porque o decorator estava na mesma linha do `return` em `api/routes/ocorrencias.py` | Quebra de linha entre o `return` e o `@router.post`, registrando a rota e restaurando o fallback (teste de regressão em TF08/TF10) |
| D02 | No modo offline, a RA “Distrito Federal” (agregado estadual) aparecia como “RA com Maior Incidência” | O agregado passou a ser excluído do ranking em `DataService.get_estatisticas`, como já ocorria no `DbService` |
| D03 | O heatmap offline calculava o peso máximo incluindo o agregado DF, e nenhum ponto chegava a 1,0 (máximo 0,347) | Normalização restrita às RAs que possuem centroide e são efetivamente plotadas; máximo voltou a 1,0 |
| D04 | A mensagem de sucesso do relatório indicava “Veja em 📁 Meus relatórios”, tela que não existe na interface | Texto ajustado para “salvo na sua conta” |
| D05 | Rodapé com erro de concordância (“Dados mais recente”) | Corrigido para “Dados mais recentes” |

---

## 3. Seção 4.2 — Teste de integração

### 4.2.1 Integração com banco de dados

Testes executados contra o PostgreSQL/PostGIS real configurado no `.env`.
Cada teste cria registros temporários com nomes únicos e os remove no final,
sem alterar a massa existente.

| ID | Integração testada | Operação | Resultado esperado | Resultado obtido |
|---|---|---|---|---|
| TI01 | Aplicação ↔ Banco (`regiao_administrativa`, `tipo_crime`, `ocorrencia_mensal`, `auth.usuario`, `auth.relatorio_salvo`) | Inserção | Registros persistidos, legíveis e com integridade referencial; senha nunca em texto puro | RA, natureza e 3 ocorrências criadas; leitura confirmou 9 ocorrências + 2 vítimas; usuário com hash bcrypt (`$2…`); relatório salvo com `id` válido |
| TI02 | Aplicação ↔ Banco | Consulta | Consultas da aplicação (SQL agregado) refletem exatamente os registros inseridos; token de sessão só como SHA-256 | `get_coropleto` = 9; `get_estatisticas` = 9 com `{jan:5, fev:4}`; 2 linhas na listagem; filtros incluem RA/crime/ano novos; token em claro não existe na tabela de sessão |
| TI03 | Aplicação ↔ Banco | Atualização | Upsert idempotente não duplica; alterações aparecem nas consultas; troca de senha invalida a anterior | Janeiro 5→8 e março inserido (3), sem duplicar (3 linhas de ocorrência, total 15); filtro pelo eixo atualizado = 9; senha antiga rejeitada e conta inativa bloqueia login |
| TI04 | Aplicação ↔ Banco | Exclusão | Exclusões removem o registro e respeitam `ON DELETE CASCADE`, sem órfãos | Ocorrência removida (3→2); exclusão da RA removeu as 2 restantes; segunda exclusão de relatório retorna 404; exclusão do usuário zerou relatórios e sessões |

### 4.2.2 Integração com APIs e serviços

O projeto utiliza serviços externos para a origem dos dados (planilhas
SSP-DF e GeoJSON público), além da integração interna painel ↔ API e da
geração de arquivos. Não foram identificadas integrações de pagamento,
e-mail ou autenticação de terceiros.

| ID | Componente | Integração | Resultado esperado | Resultado obtido |
|---|---|---|---|---|
| TI05 | API REST FastAPI ↔ cliente Streamlit (`ApiClient`) | API real em porta efêmera, consumida pelo mesmo cliente usado pelo painel; comparação com o modo offline | `check_health` online; contrato estável nos 6 endpoints; fallback devolve o mesmo schema e os mesmos totais | Health online; filtros, stats, coropleto, heatmap, ocorrências e detalhe responderam; contrato online = offline; **1.253.139** ocorrências nos dois modos |
| TI06 | Planilhas `.xls/.xlsx` da SSP-DF ↔ ETL (`ingest_crimemap`) | Consolidação de amostra real (DF, Ceilândia e Gama/2024) e da base completa de `data/raw` | CSV consolidado com colunas e totais corretos; execução idempotente | Amostra: 58 linhas e 3 RAs; base completa: **7.020 linhas, 41 RAs e 13 anos**; 1 aviso de layout (aba do DF/2021); duas execuções geraram arquivos idênticos |
| TI07 | GeoJSON público (`geodata-distrito-federal-brasil`) ↔ carga PostGIS | Leitura do cache, união de sub-regiões em RAs oficiais e verificação da fonte | Polígonos válidos mapeados para as RAs; fonte pública disponível | 44 feições → **33 polígonos oficiais**; Ceilândia válida com área > 0 e centroide no DF; requisição à fonte retornou HTTP 200 |
| TI08 | Gráficos ↔ exportação CSV/PDF (pandas + matplotlib) | Exportar a série do painel e reimportar os arquivos | CSV compatível com Excel brasileiro; PDF com gráfico e tabela | CSV com BOM UTF-8 e `;` reimportado sem perda; PDF `%PDF` com 2 páginas; nome de arquivo sem acentos/espaços |

---

## 4. Seção 4.3 — Teste de usabilidade (heurísticas de Nielsen)

A interface foi executada com `AppTest`, que renderiza a aplicação Streamlit
real e expõe os widgets e mensagens vistos pelo usuário. Aspectos
exclusivamente visuais (cores, mapa MapLibre, responsividade) não são
avaliados por esse recurso e devem ser conferidos em inspeção manual.

| Heurística | Atende? | Evidência/Justificativa |
|---|---|---|
| 1. Visibilidade do status do sistema | **Sim** | A barra lateral informa “Backend API Conectado” ou “Modo Direto Local”; há 4 cartões de KPI, contador “Mostrando 600 registros” na tabela e mensagens de sucesso ao salvar relatório |
| 2. Correspondência entre sistema e mundo real | **Sim** | Rótulos em português do domínio (“Região Administrativa (RA)”, “Eixo Indicador”, “Natureza da Ocorrência”), naturezas da SSP-DF, meses abreviados em pt-BR, milhar com ponto e fonte/período declarados no rodapé |
| 3. Controle e liberdade do usuário | **Parcial** | Abas, filtros opcionais, “Criar conta”/“← Voltar para o login”, fechar painel de detalhe e sair da conta; porém ainda não há tela para excluir relatórios nem confirmação/desfazer de exclusões |
| 4. Consistência e padrões | **Parcial** | Cartões, ícones e opções de gráfico padronizados; mesma lista de 6 tipos de gráfico na tela e na exportação. Há diferença entre os modos: com banco existem coropleto e 34 RAs; no fallback só heatmap, com 13 pontos e 14 centroides |
| 5. Prevenção de erros | **Parcial** | Login vazio avisa antes do envio; registro exige confirmação de senha e política de força; Top N limitado a 3–30 e desabilitado para Mês/Ano; parâmetros inválidos retornam 422. Falta confirmação para ações destrutivas |
| 6. Reconhecimento em vez de memorização | **Sim** | Filtros já vêm preenchidos com as opções e placeholders (“Todas as regiões do DF”, “Todos os tipos de crime”); dimensões e tipos de gráfico ficam visíveis; a aba da API lista os endpoints |
| 7. Flexibilidade e eficiência de uso | **Sim** | Quatro filtros combináveis, Top N, seis tipos de gráfico, três exportações (CSV/PDF/tabela), três estilos de mapa e uso do painel mesmo sem a API |
| 8. Design estético e minimalista | **Sim** | Conteúdo organizado em 5 abas, quatro KPIs no topo, gráficos secundários recolhidos em um único expander e paleta consistente |
| 9. Reconhecimento, diagnóstico e recuperação de erros | **Parcial** | Busca sem resultado informa “Nenhuma ocorrência encontrada”; o modo offline explica como subir o backend. Mensagens de erro da API são genéricas e não há histórico/registro de erros visível ao usuário |
| 10. Ajuda e documentação | **Parcial** | README, `SETUP_WINDOWS.md`, Swagger em `/docs`, lista de endpoints na aba “Backend API”, dica de interação do mapa e ajuda no filtro de eixo. Falta ajuda contextual para relatórios salvos e administração de usuários |

### Problemas de usabilidade encontrados

| ID | Problema identificado | Heurística relacionada | Correção realizada |
|---|---|---|---|
| PU01 | O KPI “RA com Maior Incidência” exibia “Distrito Federal”, que é o agregado estadual e não uma RA | 4. Consistência e padrões (e 2) | **Corrigido:** agregado excluído do ranking em `DataService.get_estatisticas` (mesma regra do `DbService`); passou a exibir Ceilândia |
| PU02 | No modo offline o painel não exibia KPIs: o fallback de `/api/stats` quebrava com `TypeError` e `/api/consolidar` não estava registrado | 9. Recuperação de erros (e 1) | **Corrigido:** decorator separado do `return` em `api/routes/ocorrencias.py`; rota publicada e coberta por teste de regressão |
| PU03 | No fallback, o mapa de calor não usava toda a escala: nenhum ponto chegava ao peso 1,0 (máximo 0,347) | 4. Consistência e padrões | **Corrigido:** peso normalizado apenas entre as RAs efetivamente plotadas; máximo voltou a 1,0 |
| PU04 | Ao salvar um relatório, a mensagem mandava “Veja em 📁 Meus relatórios”, tela inexistente no painel | 1. Visibilidade do status (e 9) | **Corrigido:** mensagem agora informa apenas que o relatório foi salvo na conta |
| PU05 | Rodapé com erro de concordância: “Dados mais recente” | 2. Correspondência com o mundo real | **Corrigido:** “Dados mais recentes” |
| PU06 | Não existe tela “Meus relatórios” para listar e excluir os relatórios salvos; a funcionalidade existe apenas na API | 3. Controle e liberdade (e 7) | **Não corrigido** — registrado como melhoria: criar a tela na aba “Conta & Acesso” consumindo `GET/DELETE /api/relatorios` |
| PU07 | No modo offline o filtro lista 34 RAs, mas o mapa só tem centroides para 14 (13 pontos) e não há coropleto | 4. Consistência (e 6) | **Não corrigido** — limitação documentada do fallback; exigiria base de centroides para todas as RAs |
| PU08 | Não há confirmação nem possibilidade de desfazer exclusões | 3. Controle (e 5) | **Não corrigido** — hoje a exclusão só ocorre pela API autenticada; prever confirmação na futura tela de relatórios |

---

## 5. Rastreabilidade dos testes

| Arquivo | Itens do relatório | Verificações |
|---|---|---|
| `tests/test_funcional_api.py` | TF01–TF10 | 46 |
| `tests/test_integracao_db.py` | TI01–TI04 | 11 |
| `tests/test_integracao_servicos.py` | TI05–TI08 | 14 |
| `tests/test_usabilidade.py` | Heurísticas 1–10 / PU01–PU08 | 31 |
| `tests/test_data_service.py`, `test_dados_e_auth.py`, `test_ingest_crimemap.py`, `test_load_csv.py` | Testes unitários (etapa anterior) | 49 |
| **Total** | | **151** |

Cobertura por módulo (linhas): `api/routes/relatorios.py` 100%,
`api/routes/regioes.py` 100%, `api/routes/auth.py` 88%,
`api/routes/ocorrencias.py` 81%, `api/services/data_service.py` 90%,
`db_service.py` 90%, `relatorio_service.py` 90%,
`ingest_crimemap.py` 79%, `auth_service.py` 79%,
`app/components/chart_export.py` 82%, `app/components/charts.py` 69%,
`app/main.py` 68%. **Total do projeto: 78%.**

---

## 6. Limitações e observações para o relatório

1. **Banco de dados:** os testes de integração usam a `DATABASE_URL` do `.env`.
   Nesta execução o schema `auth` ainda não existia no banco configurado; ele
   foi criado de forma idempotente (mesmo DDL de `db/auth_schema.sql`) antes
   dos testes. Sem banco, esses testes são pulados, não reprovados.
2. **Dados temporários:** os testes criam RAs/naturezas com prefixo
   `RA TESTE`/`CRIME TESTE` e contas `@teste.local`, removidas ao final.
   Uma execução interrompida pode deixar resíduos; basta repetir a limpeza
   (`DELETE ... WHERE nome LIKE 'RA TESTE %'` etc.).
3. **Rede:** o teste da fonte GeoJSON é pulado se o GitHub não responder.
   Nesta execução a fonte respondeu HTTP 200.
4. **Usabilidade:** a avaliação automatizada cobre estrutura, textos e
   comportamento dos widgets; **não** substitui a avaliação visual humana do
   mapa (PyDeck/MapLibre) nem um teste com usuários. Recomenda-se uma rodada
   manual com 3–5 participantes para as heurísticas 8 e 10.
5. **Avisos do Streamlit:** a versão 1.65 emite avisos de depreciação de
   `use_container_width` (substituir por `width`). Não afetam o usuário, mas
   devem ser tratados em manutenção futura.
6. **Funcionalidade incompleta:** a HU08 (relatórios salvos) está entregue
   pela API e pelo botão de salvar; a tela de listagem/exclusão ainda não foi
   implementada (PU06).
7. **Acessibilidade:** não foram executadas verificações automáticas de
   contraste/ARIA; a avaliação ficou restrita às heurísticas de Nielsen.
