# Data card — Temperatura do ar semanal de Recife (2016–2025)

US10.

## Resumo

| Campo | Valor |
|---|---|
| Arquivo de dados | `temperatura_se_2016_2025.csv` |
| Relatório | `temperatura_se_report.json` (fonte, parâmetros, ponto da grade, SHA-256, cobertura) |
| Fonte | Open-Meteo Historical Weather API (`https://archive-api.open-meteo.com/v1/archive`), reanálise ERA5/ERA5-Land |
| Ponto | `RECIFE_LAT`/`RECIFE_LON` de `app/config.py` (-8,05; -34,88); a API devolve a célula mais próxima, registrada em `ponto_grade` |
| Período | anos epidemiológicos CDC 2016–2025 (2016-W01 a 2025-W53, 522 semanas) |
| Grão | município × semana epidemiológica |
| Script | `backend/scripts/build_temperatura_historica.py` |

## Colunas

| Coluna | Descrição |
|---|---|
| `semana` | Semana epidemiológica CDC, `AAAASS` |
| `temp_media` | Média das temperaturas médias diárias (°C) |
| `temp_max` | Média das máximas diárias (°C) — mesma definição da feature `temp_max` do modelo |
| `temp_max_abs` | Maior máxima diária da semana (°C) |
| `dias` | Dias com média e máxima; semana com menos de 7 fica sem valores |

## Método

Uma consulta diária (`temperature_2m_mean`, `temperature_2m_max`, fuso `America/Recife`)
cobrindo do primeiro ao último dia das semanas epidemiológicas. A resposta é validada pela
mesma função da coleta do servidor (`data_sync.parse_temperatures`): datas contínuas e
valores entre -20 e 60 °C. Depois, agregação por semana CDC
(`app/ambiente/temperatura.py`).

## Escolha da fonte

Open-Meteo (e não INMET A301): série contínua desde 2016 sem lacunas, mesmo ponto e
definição já usados pelo modelo e pela coleta diária, sem depender de download manual.
A estação INMET A301 (Recife) é medição pontual com download à parte e cobertura não
avaliada aqui; fica como alternativa se o orientador exigir dado observado.

## Limitações

- Reanálise em grade (~9–25 km), não medição de estação: representa o município, não o
  bairro. Não captura ilhas de calor (US11, LST).
- A reanálise pode ser revisada; o SHA-256 e a data do download estão no relatório.
- Atribuição exigida pela licença: *Weather data by Open-Meteo.com* (CC BY 4.0).

## Regeneração

```bash
cd backend
python scripts/build_temperatura_historica.py            # usa o cache, se existir
python scripts/build_temperatura_historica.py --refresh  # baixa de novo
```

A resposta bruta fica em `app/data/cache/openmeteo_temperatura_*.json` (não versionada).
