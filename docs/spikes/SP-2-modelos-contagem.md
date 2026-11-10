# SP-2 — Modelos de contagem: Poisson vs binomial negativa (offset)

**Sprint 0 · Must · 1 pt · Squad Inteligência · Ariel Cavalcanti · 05/11/2026**

## Pergunta

Quando o alvo é uma contagem de casos por bairro × semana, quando o Poisson deixa de ser adequado e como o offset de população entra no modelo interpretável?

## Dados e método

- Painel bairro × SE (US14), 2024–2025: **9.306 observações**, **94 bairros**, **99 semanas**.
- Alvo: casos por bairro/semana; **43,4% de zeros**; média 1,94 e variância 12,46 (variância ≈ 6,4× a média).
- Covariáveis: `chuva_lag2`, `chuva_roll4`, `temp_media`, `sin(SE)` e `cos(SE)`.
- Offset: `log(população)`. **Placeholder opção A** (US08 pendente): população = 1 → offset = 0.
- Poisson via GLM; binomial negativa NB2 com `alpha` estimado por máxima verossimilhança.
- Validação temporal simples: treina em **2024**, testa em **2025**.

## Resultado

| Modelo | log-veross. | AIC | BIC | alpha | Dispersão de Pearson | MAE teste | RMSE teste | Spearman teste |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Poisson | −25.007,61 | 50.027,22 | 50.070,05 | — | **5,87** | 2,384 | 3,319 | −0,134 |
| Binomial negativa (NB2) | −16.977,08 | **33.968,16** | **34.018,13** | **1,884** | — | **2,279** | **3,196** | −0,127 |

**Leitura:** a dispersão de Pearson de 5,87 mostra sobredispersão clara; o Poisson subestima a incerteza. A NB2 reduz o AIC em ~32% e melhora MAE/RMSE no holdout. O Spearman negativo nos dois modelos revela uma **quebra estrutural entre 2024 e 2025**: o modelo treinado em 2024 superestima o início de 2025 e subestima o fim do ano. Isso não é um problema da família de contagem, e sim da especificação temporal — reforça a necessidade de rolling-origin (SP-3/US26) e de mais história (US04, 2016+).

### Offset

Com offset constante, multiplicar a população por 1000 desloca o intercepto em **−6,9078** e mantém os demais coeficientes **idênticos** (diferença 0,0); o AIC não muda. Ou seja: o mecanismo está implementado e a troca para a US08 é uma linha; o que falta é o denominador real.

### Coeficientes da NB2 (IRR com IC 95%)

| Covariável | IRR | IC 95% | Leitura |
|---|---:|---|---|
| `chuva_lag2` | 1,0016 | 1,0001 – 1,0031 | +1 mm na chuva de 2 semanas atrás → +0,16% na taxa |
| `chuva_roll4` | 0,9998 | 0,9991 – 1,0005 | sem efeito detectável |
| `temp_media` | 1,0287 | 0,9552 – 1,1078 | IC cruza 1; não significativo |
| `sin(SE)` | 1,2669 | 1,1485 – 1,3976 | sazonalidade |
| `cos(SE)` | 0,8321 | 0,7631 – 0,9074 | sazonalidade |

## Decisão e recomendação

1. **Adotar a binomial negativa NB2 com offset `log(população)` como GLM interpretável da US24.** O Poisson não é adequado para este alvo.
2. **Não usar esta especificação simples como preditor final.** O holdout mostra quebra temporal; a US24 precisa de efeitos de bairro/DS, mais história e a validação rolling-origin da US26.
3. **Levar para a US24:** coeficientes com IC, IRR, `alpha`, e comparação com o XGBoost Poisson (US25) no MLflow, sempre no mesmo esquema de validação.
4. **Assim que a US08 chegar:** trocar `carregar_populacao()` e reexecutar; nenhuma fórmula muda.

## Limitações

- População placeholder (opção A): a leitura é de contagem, não de taxa por 100 mil.
- Modelo *pooled*, sem efeitos fixos de bairro; heterogeneidade não observada fica nos resíduos.
- Sem seleção de variáveis/VIF: as duas chuvas são correlacionadas e a colinearidade não foi tratada (entra na US19).
- Semana por `DT_NOTIFIC`; a decisão `DT_SIN_PRI` × `DT_NOTIFIC` (US01) continua pendente.
- Atraso/subnotificação do SINAN não modelados.
- Validação 2024→2025 é uma checagem, não a validação final.
- Correlação não é causal; o painel é ecológico.

## Fala de 15 min (roteiro)

1. O alvo é contagem com 43% de zeros e variância 6× a média.
2. Por isso o Poisson erra a incerteza: dispersão 5,87.
3. A NB2 estima `alpha = 1,88` e reduz o AIC de 50,0 mil para 34,0 mil.
4. O offset entra como `log(população)`; com o placeholder ele é 0 e não altera a comparação.
5. O holdout 2024→2025 mostra quebra estrutural: a próxima etapa é rolling-origin e mais história, não trocar de família.

## Artefatos

- Notebook: [`backend/notebooks/sp2_glm_contagem.ipynb`](../../backend/notebooks/sp2_glm_contagem.ipynb)
- Comparação: [`sp2_comparacao_modelos.csv`](../../backend/notebooks/saidas/sp2_comparacao_modelos.csv)
- Coeficientes: [`sp2_coeficientes_nb.csv`](../../backend/notebooks/saidas/sp2_coeficientes_nb.csv)
- Validação: [`sp2_validacao_temporal.csv`](../../backend/notebooks/saidas/sp2_validacao_temporal.csv)
- Figuras: [`sp2_ajuste_2025.png`](../../backend/notebooks/saidas/sp2_ajuste_2025.png) · [`sp2_irr_nb.png`](../../backend/notebooks/saidas/sp2_irr_nb.png)
