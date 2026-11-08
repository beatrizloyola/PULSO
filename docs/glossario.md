# Glossário — linguagem ubíqua do PULSO

Termos que dados, ML e produto usam com o mesmo sentido: em código, painel, API,
tela e pitch. Os contextos citados estão no [context map](context-map.md).

**Regras de uso**

- Um termo novo, ou com sentido alterado, entra aqui no mesmo PR que o introduz.
- Nomes no código seguem o termo daqui (`semana`, `ds`, `horizonte`…). Quando o
  código divergir, a divergência fica registrada no verbete até ser corrigida.
- **Status** indica se o cálculo já está no repositório (*em uso*) ou depende de
  uma história aberta (*definido, a implementar*).

## Responsáveis e revisão

| Papel | Responsável |
|---|---|
| Squad Dados | Beatriz Loyola |
| Squad Inteligência | Pedro Bedor |
| Squad Produto | João Euclides |
| Orientador | Diego |

A revisão é feita no PR do GitHub. Um documento em `docs/` que chegou à `main`
por merge conta como revisado e aprovado pelos três squads e pelo orientador. Mudanças
posteriores seguem o mesmo caminho.

---

## Termos do acordo (US01)

### SE — Semana epidemiológica

- **Definição:** semana de domingo a sábado do calendário epidemiológico
  (sistema CDC, o mesmo do Ministério da Saúde). Um ano tem 52 ou 53 SE; a SE 1
  pode começar no fim de dezembro.
- **Formato:** inteiro `AAAASS` (ex.: `202520` = SE 20 de 2025).
- **Data de referência de um caso:** início dos sintomas (`DT_SIN_PRI`), conforme
  a [decisão 0001](decisoes/0001-semana-epidemiologica.md). Hoje o
  código ainda usa `DT_NOTIFIC`.
- **SE consolidada:** a última notificação publicada está pelo menos 4 SE depois
  dela. As SE mais recentes ficam **em consolidação** e são marcadas como incompletas.
- **Contexto:** Território (shared kernel).
- **No código:** `SemanaEpidemiologica` (`backend/app/shared/semana_epidemiologica.py`);
  coluna `semana` nos painéis; `semana_id` na API.
- **Não confundir:** semana civil ou ISO (segunda a domingo); *semana de notificação*.
- **Status:** em uso; data de referência a migrar.

### DS — Distrito Sanitário

- **Definição:** região de gestão da Secretaria de Saúde do Recife. São 8 DS
  (1 a 8), cada um com bairros inteiros; os 94 bairros cabem exatamente nos 8 DS.
  É a unidade em que a gestora distribui equipes.
- **Hierarquia:** setor censitário → bairro → DS → RPA. O DS determina a RPA
  (DS 1–2 → RPA 1, 3 → RPA 2, 4 → RPA 3, 5 → RPA 4, 6 → RPA 5, 7–8 → RPA 6).
- **Fonte de verdade:** `backend/app/data/distritos_sanitarios_*.csv`.
- **Contexto:** Território.
- **No código:** `TerritorioId.distrito_sanitario` / `.ds` (`backend/app/shared/territorio.py`);
  coluna `ds`.
- **Não confundir:** **RPA** (Região Político-Administrativa, divisão da Prefeitura,
  6 regiões) e *distrito* como no IBGE.
- **Status:** em uso.

### Incidência

- **Definição:** casos prováveis por 100 mil habitantes em um território e período.
- **Cálculo:** `incidência = casos / população × 100 000`, com SE de início de sintomas
  e população do Censo 2022 agregada de setor censitário → bairro → DS (US08). Em
  modelos de contagem, a população entra como offset `log(população)` (SP-2/US24).
- **Contexto:** Análise de Risco (consome casos de Vigilância e população de Socioterritorial).
- **Não confundir:** **contagem de casos** (sem denominador). Enquanto a US08 não
  chega, SP-4, SP-5 e o modelo atual usam contagem, que favorece bairros populosos.
  Uma tela que mostre contagem não deve rotulá-la como incidência.
- **Status:** definido, a implementar (US08).

### Canal endêmico

- **Definição:** faixa de valores esperados para cada SE, calculada a partir da
  série histórica do mesmo território. É o critério da vigilância para dizer se a
  incidência está dentro do esperado, em alerta ou em epidemia.
- **Método de referência:** para cada SE, mediana e 1º/3º quartis dos casos prováveis
  (ou da incidência) dos anos de referência. O 3º quartil é o **limite superior**
  ([Plano de Contingência Nacional, MS 2025](https://www.gov.br/saude/pt-br/centrais-de-conteudo/publicacoes/guias-e-manuais/2025/plano-de-contingencia-nacional-para-dengue-chikungunya-e-zika.pdf)).
  Os anos de referência, a exclusão de anos epidêmicos (2016, 2021 e 2025 pelo
  critério p75 da US04) e a janela de suavização ficam para a US22, que exige aprovação do orientador.
- **Contexto:** Análise de Risco.
- **Não confundir:** **ano epidêmico** (ano com total anual ≥ p75 da série; ver
  `sinan_bairro_se_report.json`), que é rótulo de ano, não de SE; **score** do modelo.
- **Status:** definido, a implementar (US22, US23).

### IPO / IDO — Índices de ovitrampa

- **IPO — Índice de Positividade de Ovitrampas:** `armadilhas com ovos / armadilhas
  examinadas × 100`. Mede a dispersão do *Aedes aegypti*: em quantos pontos há
  postura de ovos.
- **IDO — Índice de Densidade de Ovos:** `total de ovos / armadilhas com ovos`. Mede
  a intensidade nos pontos positivos.
- **Grão:** bairro × ciclo de coleta da SMS. Sempre acompanhado da cobertura (armadilhas
  ativas por DS e período); ciclo sem cobertura é ausente, não zero.
- **Contexto:** Vigilância (dado vetorial); adaptador do formato da SMS em Ingestão.
- **Não confundir:** LIRAa / Índice de Breteau (levantamento de larvas em imóveis).
- **Status:** definido, a implementar (US12, *Must condicional*; go/no-go 18/11).

### Intermitência (de abastecimento de água)

- **Definição:** dias por semana em que um bairro fica sem abastecimento de água da
  rede. Serve para testar a hipótese de que o armazenamento doméstico de água
  aumenta os criadouros.
- **Unidade:** dias/semana (0–7) por bairro.
- **Fonte:** Compesa (pedido da US03).
- **Contexto:** Socioterritorial.
- **Não confundir:** falta de chuva/estiagem; *cobertura* de rede de água.
- **Status:** definido, a implementar (US13, *Must condicional*; go/no-go 13/11).

### Ilha de calor

- **Definição:** bairro cuja temperatura de superfície (LST, Landsat 8/9, cenas
  com nuvens filtradas) está acima da média da cidade na mesma estação (seca ou chuvosa).
- **Cálculo:** anomalia de LST = LST média do bairro − LST média do Recife, por estação.
  O limiar que classifica um bairro como ilha de calor será definido na US11.
- **Contexto:** Socioterritorial.
- **Não confundir:** **temperatura do ar** semanal (Open-Meteo; features `temp_media`,
  `temp_max`), que é série temporal municipal. LST é atributo territorial por estação.
- **Status:** definido, a implementar (US11).

### Hotspot

- **Definição:** bairro classificado como **Alto-Alto (HH)** no LISA, com
  significância `p_sim < 0,05`. O bairro tem valor alto e está cercado de vizinhos
  também altos.
- **Método:** Moran global + LISA, pesos Queen linha-padronizados, 999 permutações,
  por temporada (SP-4 → US20). As outras classes LISA são coldspot (LL) e outliers (HL, LH).
- **Contexto:** Análise de Risco.
- **Não confundir:** “bairro com mais casos” ou topo da fila: um bairro com muitos
  casos pode não ser hotspot e vice-versa (SP-4: Ipsep e Caxangá são HH sem estar no
  topo absoluto). O resultado atual usa contagem, não incidência; é descritivo.
- **Status:** definido, a implementar (US20).

### Perfil territorial

- **Definição:** grupo de bairros com características socioambientais parecidas
  (vulnerabilidade, ZEIS, densidade, IDH, intermitência, LST), usado para planejar
  estratégias por tipo de território. Cada perfil tem nome em linguagem de domínio.
- **Método:** clusterização sem usar casos. Os casos entram só na validação externa
  (Kruskal-Wallis). A escolha de *k* considera silhouette, estabilidade por bootstrap
  e tamanho mínimo do grupo (SP-5 → US21; hoje Ward *k* = 3, preliminar).
- **Contexto:** Análise de Risco (variáveis vindas de Socioterritorial).
- **Não confundir:** **nível de risco** ou **hotspot**: o perfil descreve *como é* o
  território, não *quanto* risco ele tem nesta semana.
- **Status:** definido, a implementar (US21).

### Horizonte

- **Definição:** quantas SE à frente da **semana de referência** *t* a previsão
  aponta. A **semana alvo** é *t + h*.
- **Valores:** *h* ∈ {1, 2, 3, 4}.
- **Semana de referência:** a última SE com dados completos de todas as fontes; com a
  decisão 0001, a última SE consolidada.
- **Contexto:** Análise de Risco (define); Decisão Operacional (seletor na tela).
- **No código:** `config.FORECAST_HORIZONS`; parâmetro `horizonte` em `/prioridade`,
  `/mapa` e `/prioridade/explicacao`; `semana_alvo_cod` na resposta.
- **Não confundir:** “daqui a *h* semanas a partir de hoje”. A semana de referência
  pode estar atrás do calendário (ex.: dados até 2025-W52 consultados em 09/2026).
- **Status:** em uso.

### Nível de risco

- **Definição:** classificação de um território (bairro ou DS) para uma semana alvo,
  segundo a posição da incidência prevista no [canal endêmico](#canal-endêmico)
  daquele território. Responde “isso está fora do esperado?”.
- **Classes:** seguem as faixas do canal endêmico; os nomes e cortes saem da US22.
- **Contexto:** Análise de Risco (calcula); Decisão Operacional (exibe em `GET /risco/distritos`, US28/US29).
- **Não confundir:** a **classificação de prioridade** atual (Crítico ≥ 85, Alto 70–84,
  Moderado 50–69, Baixo < 50), que é um corte do **score**
  `100 · casos_previstos / (casos_previstos + 5)` em `backend/app/services/model.py`.
  Ela mede volume absoluto previsto, sem denominador nem histórico do território.
  Até a US22, a tela mostra classificação de prioridade, e não deve chamá-la de “nível de risco”.
- **Status:** definido, a implementar (US22, US28).

---

## Termos de apoio

### Bairro / território

Um dos 94 bairros oficiais do Recife, identificado por `TerritorioId`
(`backend/app/shared/territorio.py`). Nomes de qualquer fonte são normalizados
(caixa alta, sem acento) antes do join; um nome que não resolve levanta
`BairroDesconhecidoError`. **Território** é o termo genérico de produto para bairro
ou DS. Contexto: Território.

### Setor censitário

Menor unidade do Censo 2022 (IBGE). Serve apenas para agregar população e
densidade até o bairro (US08). Em `TerritorioId`, `setor_censitario` é opcional até lá.

### Caso provável

Notificação de dengue de residente no Recife (município de residência `261160`)
cuja classificação final **não** é “descartado” (código 5). É a unidade de contagem
de todas as séries. Contexto: Vigilância.

### Data de notificação / atraso de notificação

`DT_NOTIFIC`: data em que a ficha foi preenchida. **Atraso de notificação** é
`DT_NOTIFIC − DT_SIN_PRI`, em dias, e alimenta a regra de consolidação da SE.
Ver a [decisão 0001](decisoes/0001-semana-epidemiologica.md).

### Painel

Tabela analítica versionada de grão **bairro × SE** (chave `bairro_id, semana`) ou
**DS × SE** (chave `ds, semana`), com casos, clima e atributos territoriais. O schema
está em `backend/app/shared/painel_schema.py` (US14). Uma feature da semana *t* só pode
usar dados de semanas ≤ *t*.

### Score

Número de 0 a 100 derivado dos casos previstos (`config.CASOS_MEIA_SATURACAO = 5`),
usado para ordenar a fila. Não é probabilidade nem nível de risco.

### Fila de prioridades / capacidade / cobertura

- **Fila de prioridades:** territórios ordenados por score para a semana alvo (Telas 1–2).
- **Capacidade:** número de equipes disponíveis (`capacidadeEquipes`, 1–10).
- **Cobertura (operacional):** territórios do topo da fila que a capacidade atende.

Contexto: Decisão Operacional.

**“Cobertura” tem três sentidos.** Sempre qualifique:

- cobertura **operacional**: equipes × territórios;
- cobertura **de dados**: semanas com todas as fontes disponíveis;
- cobertura **de armadilhas**: ovitrampas ativas por DS/período.

### Decisão registrada

Ação que a profissional decide e registra a partir de uma recomendação (Telas 4 e 6).
O sistema recomenda; o profissional decide. Contexto: Decisão Operacional.
