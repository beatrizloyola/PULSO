# PULSO Backend

API **Flask** com XGBoost para previsão de casos de dengue e priorização dos
94 bairros de Recife. Usa chuva do portal APAC, temperatura histórica do
Open-Meteo e notificações SINAN do catálogo de Dados Abertos do Recife.

## Executar (Linux, Python 3.12)

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

Servidor em `http://localhost:8000`. A coleta é iniciada em segundo plano e
renovada diariamente por padrão. A API continua usando o último conjunto
válido enquanto a coleta acontece. Configuração, metodologia e testes em
[DADOS_APAC.md](DADOS_APAC.md).

## Histórico SINAN por bairro × semana (2016–2025)

Gera a série `app/data/sinan_bairro_se_2016_2025.csv` e o relatório
`app/data/sinan_bairro_se_report.json` a partir dos CSVs anuais de dengue do
CKAN. Os dados brutos baixados ficam em `app/data/cache/` e não são
versionados.

```bash
cd backend
python scripts/build_sinan_historico.py
```

Metodologia, colunas, filtros e limitações estão no
[data card](app/data/sinan_bairro_se_data_card.md).

## Endpoints

| Método | Rota | Conteúdo |
|---|---|---|
| GET | `/health` | Disponibilidade do modelo e lookup |
| GET | `/bairros` | Bairros, distrito, RPA e ZEIS |
| POST | `/prioridade` | Ranking, semanas disponíveis, fontes, data da coleta e avisos |
| GET | `/prioridade/<bairro_id>` | Detalhe de bairro |
| GET | `/mapa` | GeoJSON com o mesmo ranking |
| POST | `/prioridade/explicacao` | Contribuições do modelo de contagem, em escala log(casos) |

Em `/prioridade`, omita `semana_id` para a última semana com dados suficientes.
Informe `YYYY-Wnn` para consultar outra semana retornada em `semanas_disponiveis`.
`horizonte` aceita 1 a 4. Semana sem cobertura retorna HTTP 400; ausência de um
histórico suficiente retorna HTTP 503.
