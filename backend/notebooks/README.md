# Notebooks e scripts de análise — SP-2, SP-4, SP-5 e US20

Esta pasta guarda os notebooks dos spikes e o módulo `hotspots.py` da US20, do
Squad Inteligência. Eles **não** fazem parte do runtime da API nem do CI de ML:
dependem de `statsmodels` e do stack geoespacial (`geopandas`, `libpysal`,
`esda`), que não são instalados em produção.

## Ambiente

Requer Python 3.12. O caminho mais reprodutível é usar `uv`:

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install -r requirements-analysis.txt
source .venv/bin/activate
python -m ipykernel install --user --name pulso-analise --display-name "Pulso análise"
```

Se preferir `pip`:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-analysis.txt
python -m ipykernel install --user --name pulso-analise --display-name "Pulso análise"
```

## Antes de abrir os notebooks

O painel versionado (US14) é a entrada dos spikes SP-2, SP-4 e SP-5 e da
sensibilidade de fonte da US20. Gere-o uma vez:

```bash
cd backend
python scripts/gerar_painel.py
```

Saída esperada: `app/data/painel/painel_bairro_se.csv` e `painel_ds_se.csv`
(ignorados pelo git). Se o arquivo não existir, os notebooks falham com uma
mensagem pedindo esse comando.

A US20 **primária** não depende do painel: ela usa a série US04 versionada em
`app/data/sinan_bairro_se_2016_2025.csv`. Sem o painel, o script gera tudo,
exceto `us20_sensibilidade_fonte.csv`, e avisa no log.

## Executar

```bash
cd backend
jupyter lab notebooks/
# ou, sem abrir a interface:
jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.kernel_name=pulso-analise \
  notebooks/sp2_glm_contagem.ipynb
```

| Arquivo | Spike/História | Saídas principais |
|---|---|---|
| `sp2_glm_contagem.ipynb` | GLM Poisson vs binomial negativa + offset | comparação de modelos, IRR, validação temporal |
| `sp4_moran_lisa.ipynb` | Moran global + LISA (2024) | mapa LISA, GeoJSON classificado, diagrama de Moran |
| `sp5_clusters_k.ipynb` | Ward, silhouette e escolha de k | dendrograma, silhouette, mapa de perfis, tabela de k |
| `../scripts/gerar_hotspots.py` | US20: Moran + LISA por temporada | GeoJSONs `us20_lisa_<temporada>.geojson`, CSVs, mapas e `us20_meta.json` |

> **Escopo por branch:** os notebooks são entregues em branches separadas
> (`feature/sp2-glm-contagem`, `feature/sp4-moran-lisa` e `feature/sp5-clusters-k`).
> Se um notebook da tabela não existir na branch atual, ele pertence a outra
> branch do mesmo conjunto.

Figuras, tabelas e GeoJSON vão para `notebooks/saidas/`. Os resumos de 1 página
ficam em [`docs/spikes/`](../../docs/spikes/).

## US20 — hotspots por temporada

O script `scripts/gerar_hotspots.py` lê a série US04, roda Moran global + LISA
por temporada e grava os artefatos `us20_*` em `notebooks/saidas/`:

```bash
cd backend
source .venv/bin/activate
python scripts/gerar_hotspots.py
# ou só algumas temporadas:
python scripts/gerar_hotspots.py --temporadas 2024,2025 --permutacoes 999
```

O padrão é 2016–2025, Queen linha-padronizada, 999 permutações e seed 42. A
sensibilidade de fonte roda US04 × painel em 2024–2025 e só é gerada se o painel
existir. Resumo e decisões em
[`docs/spikes/US20-hotspots-por-temporada.md`](../../docs/spikes/US20-hotspots-por-temporada.md).

## População (opção A)

Enquanto a US08 (Censo 2022) não chega, `_comum.carregar_populacao()` devolve
**1 habitante por bairro**. Consequências:

- SP-2: `offset = log(1) = 0`; a leitura é de contagem, não de taxa.
- SP-4: o LISA roda sobre casos; o padrão espacial é o mesmo de uma taxa com
  denominador constante, mas bairros populosos são favorecidos.
- SP-5: não há densidade; usamos área como proxy.
- US20: o LISA roda sobre casos; a classificação HH/LL é invariante a um
  denominador constante, mas a leitura de risco por bairro não é.

Quando a tabela oficial existir, troque **apenas** a implementação de
`carregar_populacao()` (e, se quiser separar, o nome da coluna `populacao`).
Nenhuma fórmula dos notebooks muda. Reexecute os três notebooks e a US20,
e atualize os resumos.

## Regras

- Não mover `app/services/forecaster.py` nem o pickle do modelo por causa dos
  notebooks.
- Não adicionar essas dependências ao `requirements.txt` de produção/CI.
- A US20 lê a série US04 versionada; ela não altera o painel nem o pipeline de
  produção.
- Dados brutos não entram no git; `notebooks/saidas/` e os resumos entram.
