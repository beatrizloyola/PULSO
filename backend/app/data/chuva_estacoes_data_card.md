# Data card — Chuva por estação e por Distrito Sanitário (APAC + CEMADEN), 2016–2025

US05 (chuva por estação e por DS), US06 (integração CEMADEN) e US07 (reconciliação APAC × CEMADEN).

## Resumo

| Campo | Valor |
|---|---|
| Inventário | `estacoes_chuva_recife.csv` |
| Série por estação | `chuva_estacao_se_2016_2025.csv` (estação × SE) |
| Série por DS | `chuva_ds_se_2016_2025.csv` (DS × SE) |
| Relatório | `chuva_estacoes_report.json` (proveniência, método, cobertura, reconciliação) |
| CEMADEN (Recife) | `cemaden_recife/cemaden_recife_AAAA_MM.csv.gz` — extratos mensais versionados |
| Período | anos epidemiológicos CDC 2016–2025 (2016-01-03 a 2026-01-03) |
| Unidade | mm acumulados na semana epidemiológica |
| Script | `backend/scripts/build_chuva_estacoes.py` |
| Código | `app/ingestao/cemaden.py` (ACL), `app/ambiente/{estacoes,espacializacao,reconciliacao}.py` |

## Fontes

- **APAC** — Histórico Pluviométrico diário de Recife, o mesmo formulário usado pela
  coleta do servidor (`app/services/apac_client.py`), uma consulta por ano civil.
  A APAC publica estações próprias e de redes parceiras, incluindo o CEMADEN, com o
  código da rede de origem.
- **CEMADEN, leituras** — CSV mensal do Mapa Interativo
  (<https://mapainterativo.cemaden.gov.br/> → *Download - Dados Pluviométricos*,
  `/download/download_form.php`). O formulário tem captcha, então o download é manual:
  UF `PE` e município `RECIFE` (UF inteira também serve), mês e ano; salve cada arquivo
  em `backend/app/data/cache/cemaden/` (qualquer nome `*.csv`, não versionado). O script
  copia só as linhas de Recife, sem alterá-las, para
  `app/data/cemaden_recife/cemaden_recife_AAAA_MM.csv.gz` (versionado, ~60 KB/mês) e lê a
  série desses extratos; quem clona o repositório regenera tudo sem os downloads.
  Horários em UTC; cada linha é o acumulado de um intervalo (10 min com chuva, 1 h sem
  chuva) que termina em `datahora`.
  O adaptador aceita os dois cabeçalhos já publicados (`codEstacao;...;valorMedida` e
  `COD_ESTACAO;...;MEDIDA`) e decimal com vírgula ou ponto.
  Os formulários `download_form.php?type=5` e `?type=10` são de PCDs Acqua e
  geotécnicas, não de pluviômetros.
- **CEMADEN, cadastro** — `https://resources.cemaden.gov.br/dados/311_24.json`
  (código, nome, lat/lon, rede) das estações de Recife.
- **Coordenadas das estações só da APAC** (fora do cadastro CEMADEN): APAC, *Atlas
  Climatológico de Pernambuco* (normais 1991–2020) para os postos convencionais
  Várzea, Santo Amaro (publicado pela APAC como "Codecipe / Santo Amaro") e Alto da
  Brasileira, com 3 casas decimais (~100 m); ANA HidroInventário (estação 834020) para a
  sede da APAC. A fonte de cada coordenada fica em `fonte_coordenada`.
- **DS** — polígonos dos 94 bairros (`bairros_esig.geojson`) agrupados pelo DS da tabela
  da Secretaria de Saúde (`app/shared/territorio.py`). O código de DS dos arquivos GIS
  (`CDISTSANTPSAD`, `distritos_sanitarios_*.geojson`) troca DS VII e DS VIII em 14 bairros
  (ex.: Guabiraba é DS VIII na tabela e DS VII no GIS); a tabela prevalece porque é a
  usada pelo painel e pelo SINAN.

## Colunas

### `estacoes_chuva_recife.csv`

| Coluna | Descrição |
|---|---|
| `codigo` | Código da estação (GMMC na APAC = código CEMADEN; sufixo `A` automática, `V` convencional, `G` geotécnica) |
| `nome`, `latitude`, `longitude`, `fonte_coordenada` | Identificação e origem da coordenada |
| `rede` | Rede de origem: `CEMADEN` (código no cadastro ou no download CEMADEN) ou `APAC` |
| `tipo` | `automatica`, `convencional` ou `geotecnica` |
| `rotulo_apac` | Rótulo no nome publicado pela APAC (`APAC`, `CEMADEN`, `Convencional`). Não define a rede: Nova Descoberta e Guabiraba aparecem como `[APAC]`, mas são do CEMADEN |
| `publicada_apac`, `publicada_cemaden` | Há leituras da estação em cada fonte |
| `inicio`, `fim`, `dias_com_leitura` | Período com leitura no recorte 2016–2025 (vazio = cadastrada, sem leitura) |
| `ds` | DS que contém a estação |

### `chuva_estacao_se_2016_2025.csv`

`codigo`, `semana` (AAAASS), `chuva_mm` (vazio se a semana não tem os 7 dias), `dias`
(dias com leitura) e `dias_cemaden` (dias vindos do CEMADEN, não da APAC).

### `chuva_ds_se_2016_2025.csv`

| Coluna | Descrição |
|---|---|
| `ds`, `semana` | Chave única (8 DS × 522 SE) |
| `chuva_mm` | Soma semanal da chuva diária do DS; **vazio quando `completa` é falso** |
| `completa` | 7 dias com estimativa e `falha` ≤ 0,2 |
| `falha` | Fração média da área do DS sem leitura da própria estação na semana (0 a 1) |
| `dias_com_estimativa` | Dias em que alguma estação mediu |
| `n_estacoes` | Máximo de estações com peso no DS num dia da semana |
| `dist_media_km` | Distância média da área do DS à estação usada (representatividade) |

## Método

### Deduplicação e precedência (US06/US07)

1. **Mesma estação = mesmo código.** A APAC republica estações CEMADEN com o código do
   CEMADEN; por isso o código deduplica as fontes. Estações co-localizadas com códigos
   diferentes (ex.: posto convencional e automática do mesmo bairro) são instrumentos
   distintos e entram como pares próximos na reconciliação, não como duplicatas.
2. **Precedência:** havendo leitura APAC para a estação/dia, ela vale (`origem = APAC`).
3. **Preenchimento de lacunas:** sem leitura APAC, vale o total diário do CEMADEN da mesma
   estação (`origem = CEMADEN`), somente se o dia teve transmissão em ao menos 22 das 24
   horas. Dia mais curto fica ausente, nunca é a soma parcial.
4. Sem as duas fontes, o dia fica ausente. Não há preenchimento a partir de outra
   estação na série por estação; a série por DS trata ausência como falha (abaixo).
5. **Dia pluviométrico:** o dia D da APAC é o acumulado de 24 h que termina às **07h de
   Recife (10h UTC) de D**, a leitura padrão de pluviômetro (ANA). O total CEMADEN usa a
   mesma janela (`FIM_DIA_UTC_H = 10`). Em 2016–2019, a correlação diária média das
   automáticas CEMADEN com os postos convencionais APAC a até 3 km (12 pares), por hora
   de fechamento do dia: 05h 0,844 · 06h 0,883 · **07h 0,898** · 08h 0,897 · 09h 0,883 ·
   10h 0,865 · 11h 0,822; dia civil (00h–24h) 0,562. Com 2020, 2022 e 2023 (14 pares): 07h
   0,890 · 08h 0,799 · 09h 0,764 · dia civil 0,492. As duplicatas de 2024 em diante
   (mesma estação nas duas fontes) confirmam ou corrigem isso; ver `convencoes_dia` no
   relatório, recalculado a cada geração.
6. **Leitura implausível:** leitura acima de 50 mm num único registro (≤ 1 h) é acumulado
   despejado após falha de transmissão, não chuva do intervalo (ex.: 194 mm em 601A às
   03:10 UTC de 14/06/2019, após 3 semanas sem dado). O dia todo fica ausente; os casos
   ficam em `metodo.dias_leitura_suspeita` no relatório.
7. **Sensor seco:** pluviômetro entupido ou travado reporta zero enquanto chove em volta
   (ex.: Brega e Chique 603G com 0 mm em mai–out/2025; Várzea 605A com 0 mm em jun/2023,
   mediana da cidade 429 mm). Em cada janela de 30 dias com ao menos 20 leituras, a chuva
   média da estação é comparada com a mediana das vizinhas a até 5 km (ao menos 2 com
   janela válida; senão, a mediana das demais estações da cidade). Se a referência soma
   30 mm ou mais e a estação fica abaixo de 10% dela, os dias da janela saem da série:
   viram falha na espacialização, não chuva zero. Os trechos removidos ficam em
   `metodo.sensor_seco.trechos_removidos` (39 trechos, ~3,1 mil estação-dias em 2016–2025).

A flag de origem por medição fica no diário consolidado
`app/data/cache/chuva_estacao_dia.csv` (não versionado) e se resume em `dias_cemaden`.

### Chuva por DS (US05)

Polígonos de Thiessen (Voronoi) discretizados: uma grade de ~275 m (0,0025°) cobre os
DS; a cada dia, cada ponto recebe a chuva da estação mais próxima **entre as que mediram
naquele dia**, e a chuva do DS é a média dos pontos (média das estações ponderada pela
área de Thiessen dentro do DS). Os pesos com a rede completa estão em
`pesos_thiessen_rede_completa` no relatório.

**Falha:** fração da área do DS cuja estação mais próxima **em operação** não mediu no
dia. Em operação = entre a primeira e a última leitura publicada pela APAC ou, no
CEMADEN, entre a primeira e a última leitura **dentro dos meses baixados**: mês sem
arquivo não é falha da estação, só deixa a área com uma estação mais distante (visível
em `dist_media_km`). Silêncio de mais de 365 dias encerra o período (a estação estava
desativada: o dia isolado que o posto Várzea 601V publica em jun/2024, após dois anos
mudo, não torna 2022–2023 falha). Estação antes da instalação ou depois da desativação
não conta como falha; dia removido pelo QC (leitura implausível, sensor seco) conta.
Dia sem nenhuma estação conta como falha total.
Semana com falha média acima de **0,2** ou com dia sem estimativa fica `completa = False`
e `chuva_mm` vazio — nada é preenchido em silêncio. Os limites estão em
`app/ambiente/espacializacao.py` (`LIMITE_FALHA`) e `app/ingestao/cemaden.py`
(`HORAS_MIN_DIA`).

### Reconciliação (US07)

O relatório traz:

- `estacoes_duplicadas`: para a mesma estação nas duas fontes, dias comuns, Pearson,
  Spearman, viés e MAE (CEMADEN − APAC), % de dias com diferença ≤ 0,2 mm e dias
  divergentes (> 1 mm e > 10%);
- `pares_proximos`: estações distintas a até 3 km com ≥ 30 dias comuns, com correlação
  diária e semanal (semanas com os 7 dias);
- `estacoes_vs_vizinhas`: mediana da correlação diária de cada estação com as vizinhas;
  abaixo de 0,5 a estação é marcada `revisar` (não é excluída).

## Cobertura e limitações

- **A APAC só publica as automáticas do CEMADEN a partir de 2024.** Sem o CEMADEN, a
  série depende de 2–3 postos convencionais, com a área do DS a ~4,7 km da estação usada
  (caso de 2021, o único ano ainda sem CEMADEN). Ver `cobertura_ds_por_ano`.
- **CEMADEN nesta versão: 2016 a 2020, 2022 e 2023 completos** (84 meses; 17–21
  estações de Recife por mês, mais as geotécnicas a partir de out/2019). A distância
  média da área do DS à estação fica em ~1,8–2,3 km e cada DS usa ~6 estações.
  DS-semanas completas: 93,3% (2016), 82,9% (2017), 76,7% (2018), 59,6% (2019), 72,4%
  (2020), 95,7% (2021, só APAC), 73,8% (2022), 62,5% (2023), 66,3% (2024) e 51,2% (2025).
  As incompletas vêm de silêncios longos de estações que depois voltam (ex.: Alto Mandu
  610A de 2016-W41 a 2017-W28; Guabiraba 612A de 2017-W33 a 2018-W16, DS VIII) e,
  desde a versão com o filtro de sensor seco, dos trechos removidos — que antes entravam
  como zero. 2025 é o caso mais forte: 603G, 613A, 617A e 620A ficam secos por meses
  (DS I, III, IV e V abaixo de 35% de semanas completas). jan/2024 e 2021 ainda faltam
  no CEMADEN; fev/2024–2025 acrescentaria estações que a APAC não publica (Ibura 615A,
  Córrego do Jenipapo 608A...) e as primeiras duplicatas para `estacoes_duplicadas`.
- A sede da APAC (623A, "RECIFE - APAC") transmite pela plataforma do CEMADEN desde
  out/2017: aparece no download, mas a rede continua `APAC`.
- O posto Várzea (601V) não tem leitura de 2022 a mai/2024.
- Estações fora do cadastro atual têm a coordenada do próprio download: 604A (USF Alto
  Bela Vista-Ibura), 616A (Várzea), 622A (Boa Vista) e as geotécnicas 605G, 607G–610G.
- `revisar` não marca nenhuma estação depois do filtro de sensor seco. UR12-Cohab (609G)
  passa de mediana 0,07 para 0,70 (estava em 0 mm de dez/2021 a mar/2023); a correlação
  ~0 de Brega e Chique (603G) com Várzea (601A) vinha dos zeros de 2024–2025.
- Pluviômetros medem pontos: a chuva por DS é uma estimativa espacial, não medição.

## Regeneração

```bash
cd backend
python scripts/build_chuva_estacoes.py            # usa o cache, se existir
python scripts/build_chuva_estacoes.py --refresh  # baixa de novo APAC e cadastro CEMADEN
```

HTMLs da APAC, cadastro CEMADEN, downloads brutos do CEMADEN e o diário consolidado
ficam em `app/data/cache/` e não são versionados; os extratos de Recife do CEMADEN, sim.
