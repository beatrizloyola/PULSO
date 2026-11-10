# Notebooks de análise — spikes SP-2, SP-4 e SP-5

Esta pasta guarda os notebooks dos spikes do Squad Inteligência. Eles **não**
fazem parte do runtime da API nem do CI de ML: dependem de `statsmodels` e do
stack geoespacial (`geopandas`, `libpysal`, `esda`), que não são instalados em
produção.

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

O painel versionado (US14) é a entrada de todos os spikes. Gere-o uma vez:

```bash
cd backend
python scripts/gerar_painel.py
```

Saída esperada: `app/data/painel/painel_bairro_se.csv` e `painel_ds_se.csv`
(ignorados pelo git). Se o arquivo não existir, os notebooks falham com uma
mensagem pedindo esse comando.

## Executar

```bash
cd backend
jupyter lab notebooks/
# ou, sem abrir a interface:
jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.kernel_name=pulso-analise \
  notebooks/sp2_glm_contagem.ipynb
```

| Notebook | Spike | Saídas principais |
|---|---|---|
| `sp2_glm_contagem.ipynb` | GLM Poisson vs binomial negativa + offset | comparação de modelos, IRR, validação temporal |
| `sp4_moran_lisa.ipynb` | Moran global + LISA | mapa LISA, GeoJSON classificado, diagrama de Moran |
| `sp5_clusters_k.ipynb` | Ward, silhouette e escolha de k | dendrograma, silhouette, mapa de perfis, tabela de k |

Figuras, tabelas e GeoJSON vão para `notebooks/saidas/`. Os resumos de 1 página
ficam em [`docs/spikes/`](../../docs/spikes/).

## População (opção A)

Enquanto a US08 (Censo 2022) não chega, `_comum.carregar_populacao()` devolve
**1 habitante por bairro**. Consequências:

- SP-2: `offset = log(1) = 0`; a leitura é de contagem, não de taxa.
- SP-4: o LISA roda sobre casos; o padrão espacial é o mesmo de uma taxa com
  denominador constante, mas bairros populosos são favorecidos.
- SP-5: não há densidade; usamos área como proxy.

Quando a tabela oficial existir, troque **apenas** a implementação de
`carregar_populacao()` (e, se quiser separar, o nome da coluna `populacao`).
Nenhuma fórmula dos notebooks muda. Reexecute os três notebooks e atualize os
resumos.

## Regras

- Não mover `app/services/forecaster.py` nem o pickle do modelo por causa dos
  notebooks.
- Não adicionar essas dependências ao `requirements.txt` de produção/CI.
- Dados brutos não entram no git; `notebooks/saidas/` e os resumos entram.
