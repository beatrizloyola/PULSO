# Spikes — Inteligência

Resumos de 1 página dos spikes do Squad Inteligência, para a sessão com o
orientador. Cada resumo aponta para o notebook executável e para as saídas em
`backend/notebooks/saidas/`.

| Spike | Tema | Sprint | Status | Resumo |
|---|---|---|---|---|
| **SP-2** | Modelos de contagem: Poisson vs binomial negativa, offset | S0 | ✅ concluído | [SP-2-modelos-contagem.md](SP-2-modelos-contagem.md) |
| **SP-4** | Estatística espacial: Moran global e LISA | S1 | ✅ concluído | [SP-4-estatistica-espacial.md](SP-4-estatistica-espacial.md) |
| **SP-5** | Clusterização e escolha de k | S1 | ✅ concluído | [SP-5-clusterizacao-k.md](SP-5-clusterizacao-k.md) |

## Como reproduzir

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install -r requirements-analysis.txt
source .venv/bin/activate
python -m ipykernel install --user --name pulso-analise --display-name "Pulso análise"
python scripts/gerar_painel.py
jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.kernel_name=pulso-analise \
  notebooks/sp2_glm_contagem.ipynb notebooks/sp4_moran_lisa.ipynb notebooks/sp5_clusters_k.ipynb
```

Detalhes em [`backend/notebooks/README.md`](../../backend/notebooks/README.md).

## Decisões que os três spikes destravam

- **US24 (GLM binomial negativa):** NB2 com offset `log(população)` é o modelo
  interpretável; o Poisson não serve (dispersão 5,87).
- **US20 (hotspots LISA):** Moran global + LISA (Queen, 999 permutações); 10 HH
  em 2024, concentrados nos DS 4, 5, 6 e 8.
- **US21 (perfis territoriais):** Ward com k=3 é o único admissível com os
  proxies atuais; reexecutar com IDH, densidade, intermitência e LST.

## Pendências que afetam os três

| Pendência | História | Efeito |
|---|---|---|
| População por bairro | US08 | offset do SP-2, incidência do SP-4, densidade do SP-5 |
| IDH | US09 | variável do SP-5 / US21 |
| Intermitência de água | US13 | variável do SP-5 / US21 |
| LST / ilhas de calor | US11 | variável do SP-5 / US21 |
| Decisão `DT_SIN_PRI` × `DT_NOTIFIC` | US01 | semana epidemiológica de todos |
| Histórico SINAN 2016+ | US04 | validação temporal do SP-2 / US26 |

Enquanto a US08 não chega, os três resultados são **preliminares** e estão
rotulados como tal nos resumos.

> O plano canônico continua em [`docs/Plano de ação PULSO (Scrum + DDD).md`](<../Plano de ação PULSO (Scrum + DDD).md>).
> O link `docs/PLANEJAMENTO.md` citado nos cartões do Linear ainda não existe no
> repositório.
