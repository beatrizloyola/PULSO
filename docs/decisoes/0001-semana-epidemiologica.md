# 0001 — Data de referência da semana epidemiológica: `DT_SIN_PRI`

| Campo | Valor |
|---|---|
| Status | **Aceita** — vale a partir do merge na `main` ([regra de revisão](../glossario.md#responsáveis-e-revisão)) |
| Data | 08/11/2026 |
| História | US01 (PUL-5) |
| Contexto | Governança · afeta Vigilância, Análise de Risco e Decisão Operacional |
| Termos | [SE](../glossario.md#se--semana-epidemiológica), [canal endêmico](../glossario.md#canal-endêmico), [horizonte](../glossario.md#horizonte) |

## Decisão

A **SE de um caso** é a semana epidemiológica (calendário CDC/MS, `SemanaEpidemiologica`)
da **data de início dos sintomas**: `DT_SIN_PRI` (arquivos 2021+) /
`dt_diagnostico_sintoma` (arquivos 2016–2020). Ela é a SE de todo painel, série,
canal endêmico, correlação defasada e alvo de modelo.

`DT_NOTIFIC` / `dt_notificacao` continua no domínio só como **data de notificação**,
para medir atraso (oportunidade de notificação) e para decidir se uma SE está
consolidada. Não é usada para posicionar casos no tempo.

**Regra de consolidação:** uma SE só é **consolidada** quando a data da última
notificação publicada está pelo menos **4 SE** depois dela. As SE mais recentes ficam
**em consolidação**: aparecem marcadas como incompletas, nunca são tratadas como
queda real de casos e não definem a semana de referência do modelo.

## Por que

1. **É o padrão da vigilância de arboviroses.** O diagrama de controle do Sinan
   seleciona casos prováveis pela semana epidemiológica dos primeiros sintomas
   ([nota técnica Sinan — diagrama de controle/dengue, SES-RJ](https://sistemas.saude.rj.gov.br/tabnetbd/Sinan/Dengue_Diagrma_Controle.pdf)),
   e o [Plano de Contingência Nacional para Dengue, Chikungunya e Zika (MS, 2025)](https://www.gov.br/saude/pt-br/centrais-de-conteudo/publicacoes/guias-e-manuais/2025/plano-de-contingencia-nacional-para-dengue-chikungunya-e-zika.pdf)
   define o canal endêmico por SE sobre esses casos. A US22 exige “critério
   reconhecido pela vigilância”; a SE de notificação não atende a isso.
2. **É o tempo biológico.** O que importa para chuva → criadouro → vetor → caso é
   a infecção, e o início dos sintomas está mais próximo dela. A notificação acrescenta
   um atraso operacional variável (mediana de 4–7 dias, cauda longa) que mistura
   o efeito do clima com a capacidade da rede de saúde. Isso afeta diretamente as
   correlações defasadas (SP-1/US17) e as features com lag do modelo.
3. **O dado existe e está completo.** Medido nos CSVs anuais do CKAN Recife (residentes
   em Recife, sem os descartados, como em `build_sinan_historico.py`):

| Ano | Casos | Data de sintomas nula | Atraso mediano (dias) | p90 (dias) | Na mesma SE | Até 2 SE | Até 4 SE |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2016 | 13.702 | 0% | 7 | 43 | 30% | 73% | 84% |
| 2017 | 966 | 0% | 6 | 22 | 30% | 86% | 93% |
| 2018 | 1.219 | 0% | 6 | 21 | 32% | 87% | 95% |
| 2019 | 4.699 | 0% | 5 | 24 | 32% | 86% | 93% |
| 2020 | 1.620 | 0% | 5 | 20 | 39% | 88% | 96% |
| 2021 | 7.398 | 0% | 7 | 55 | 28% | 73% | 81% |
| 2022 | 1.354 | 0% | 7 | 42 | 25% | 75% | 85% |
| 2023 | 3.523 | 0% | 4 | 19 | 39% | 89% | 95% |
| 2024 | 2.607 | 0% | 5 | 18 | 34% | 90% | 96% |
| 2025 | 5.654 | 0% | 5 | 17 | 33% | 90% | 96% |

   “Na mesma SE / até k SE” é a parcela dos casos notificados até k semanas depois
   da SE de início de sintomas. Nenhum registro tem notificação antes dos sintomas.
   Em `SEM_PRI` (2024–2025), 100% dos registros batem com a SE CDC calculada a
   partir de `DT_SIN_PRI`.

   **Só 25–39% dos casos são notificados na própria SE de sintomas.** Com
   `DT_NOTIFIC`, a maior parte dos casos fica uma ou mais semanas depois do momento
   em que adoeceu.

## Alternativa rejeitada: `DT_NOTIFIC`

O único ganho é que a SE de notificação “fecha” assim que a semana termina, sem
atraso de digitação. Ele não compensa: a série fica deslocada e suavizada pelo atraso,
o canal endêmico deixa de ser comparável com o da vigilância, e o atraso varia entre
anos (p90 de 17 a 55 dias) e cresce justamente nos anos epidêmicos (2016, 2021).

## Consequências

- **Atraso nas SE recentes.** Em 2024–2025, ~4% dos casos ainda chegam depois de 4 SE;
  nos anos epidêmicos, 16–19%. O corte de 4 SE é uma regra operacional, não uma
  garantia de completude. A US15 (qualidade de dados) deve acompanhar o percentual
  por ano.
- **Semana de referência do modelo.** A semana de referência *t* de uma previsão é a
  última SE consolidada, e o [horizonte](../glossario.md#horizonte) *h* conta a partir
  dela. Uma previsão de *h* = 1 pode, então, apontar para uma SE que já passou no
  calendário mas ainda está em consolidação. A tela deve deixar isso explícito (US31).
  Estimar as SE em consolidação (*nowcasting*) fica fora do escopo atual.
- **Código a migrar (hoje usa notificação):**
  - `backend/app/services/data_sync.py` — `normalize_sinan` calcula a SE a partir de `DT_NOTIFIC`;
  - `backend/scripts/build_sinan_historico.py` e `sinan_bairro_se_2016_2025.csv` —
    `col_semana` = `ds_semana_notificacao` / `SEM_NOT` (ver data card);
  - painel (US14) e modelo servido (`forecast_meta.json`) — regenerar e retreinar depois.
  - Os spikes SP-1 a SP-5 rodaram sobre a SE de notificação e devem ser lidos como preliminares nesse ponto.
- `backend/DADOS_APAC.md` e o data card do SINAN passam a citar esta decisão quando
  a migração acontecer.

## Reprodução

Os números da tabela vêm dos CSVs “Casos de Dengue AAAA” do dataset
`3c990c15-29ad-46e5-8fd2-1b83289bb9f5` (CKAN Recife), consultados em 08/11/2026.
Filtros: município de residência = 261160 e classificação final ≠ 5. Datas em
`dd/mm/aaaa` (2021–2022, 2024–2025) e `aaaa-mm-dd` (2016–2020, 2023) são lidas com
o formato explícito de cada uma. A SE é calculada com `epiweeks` (sistema CDC).

## Revisão

Revisada no PR do GitHub por Squad Dados (Beatriz Loyola), Squad Inteligência
(Pedro Bedor), Squad Produto (João Euclides) e orientador (Diego). O merge na `main`
registra a aprovação. Para revogar ou substituir esta decisão, abra uma nova decisão
que a cite.
