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

## IDH por bairro (Atlas Brasil)

`app/data/idh_atlas_2010.json` (gerado por `python -m scripts.build_idh_atlas`)
traz o IDHM 2010 do Atlas Brasil, publicado por Unidade de Desenvolvimento
Humano (UDH), agregado para os 94 bairros do Recife. É contexto
socioeconômico — não é variável do modelo de previsão.

**Limitação:** quando uma UDH abrange mais de um bairro, sua população é
dividida igualmente entre eles e o mesmo IDH é repetido para todos — não é um
valor exclusivo de cada bairro. O campo `udhs_compartilhadas` em cada entrada
de `bairros` conta quantas das UDHs daquele bairro são compartilhadas dessa
forma; vários bairros com esse campo > 0 vão exibir o mesmo IDH entre si
(ex.: Santana, Poço e Casa Forte, que caem na mesma UDH).
