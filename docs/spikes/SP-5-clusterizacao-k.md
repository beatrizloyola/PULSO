# SP-5 — Clusterização de bairros e escolha de k

**Sprint 1 · Should · 1 pt · Squad Inteligência · Ariel Cavalcanti · 05/11/2026**

## Pergunta

Os 94 bairros do Recife se organizam em quantos perfis territoriais? Qual k é defensável com as variáveis disponíveis hoje?

## Dados e método

- Unidade: **bairro** (n = 94).
- Variáveis da clusterização (somente territoriais, padronizadas):
  - `vulnerabilidade_score` (ZEIS, 25–100);
  - `log1p(zeis_ha)`;
  - `log1p(area_km2)` (área do polígono em SIRGAS 2000 / UTM 25S).
- **Casos ficam fora da clusterização** e entram apenas como validação externa (Kruskal-Wallis), para não criar circularidade.
- Algoritmo: **Ward** (hierárquico). Comparação com k-means apenas como checagem.
- Escolha de k: silhouette para k = 2..8 + estabilidade por **bootstrap** (30 reamostragens, ARI contra a solução completa).
- Critérios de admissibilidade definidos antes de olhar o resultado: **menor cluster ≥ 10** e **ARI mínimo ≥ 0,4**. Entre os admissíveis, maior silhouette.

## Resultado

| k | Silhouette (Ward) | Menor cluster | Tamanhos | ARI médio | ARI mínimo |
|---:|---:|---:|---|---:|---:|
| 2 | 0,571 | 26 | [68, 26] | 0,667 | **0,174** |
| **3** | **0,468** | **19** | **[26, 49, 19]** | **0,768** | **0,496** |
| 4 | 0,505 | 6 | [49, 6, 19, 20] | 0,838 | 0,523 |
| 5 | 0,528 | 6 | [6, 20, 19, 12, 37] | 0,820 | 0,624 |
| 6–8 | 0,523–0,541 | 1 | — | — | — |

**k = 3 é o único admissível:** k=2 falha na estabilidade (ARI mínimo 0,174 < 0,4); k≥4 falha no tamanho do menor cluster (6 ou 1). O silhouette de k=3 (0,468) é moderado, mas é o que os proxies atuais sustentam.

### Perfis encontrados (médias em unidade original)

| Perfil | n | Casos médios | Casos/km² | Vulnerabilidade | ZEIS (ha) | Área (km²) | % com ZEIS |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Perfil 1 — alta vulnerabilidade, ZEIS, território extenso** | 26 | 172,4 | 67,8 | 90,0 | 54,7 | 5,36 | 96% |
| **Perfil 2 — baixa vulnerabilidade, sem ZEIS, território compacto** | 49 | 50,8 | 70,3 | 25,0 | 0,0 | 0,92 | 0% |
| **Perfil 3 — vulnerabilidade intermediária, ZEIS residual** | 19 | 113,8 | 71,3 | 63,4 | 3,0 | 1,87 | 89% |

**Validação externa:** Kruskal-Wallis dos casos médios entre os 3 clusters: **H = 24,66, p = 4,4 × 10⁻⁶**. Os perfis se diferenciam em casos, mas parte da diferença é tamanho populacional (não temos denominador).

### Sensibilidade

| Especificação | Silhouette (k=3) | Tamanhos |
|---|---:|---|
| Territorial (primário) | 0,468 | [26, 49, 19] |
| + histórico de surto | 0,584 | [25, 59, 10] |
| + casos médios (circular) | 0,313 | [27, 54, 13] |

Incluir o histórico de surto aumenta o silhouette, mas o histórico é derivado do próprio desfecho — por isso fica fora do modelo primário. Incluir casos derruba o silhouette e cria circularidade explícita.

## Decisão e recomendação

1. **Usar Ward com k = 3 como ponto de partida da US21**, com a regra de admissibilidade documentada (silhouette + estabilidade + tamanho mínimo).
2. **Não tratar os nomes dos perfis como definitivos.** Eles descrevem proxies (vulnerabilidade/ZEIS/área), não o risco final.
3. **Reexecutar na S2** quando chegarem IDH (US09), densidade (US08), intermitência (US13) e LST (US11). Espera-se que o k e os nomes mudem.
4. **Levar para a US21:** dendrograma, curva de silhouette, ARI bootstrap e Kruskal-Wallis como critérios de aceite do perfil, não só o mapa.

## Limitações

- Só três proxies territoriais, dois deles quase discretos (vulnerabilidade e ZEIS); o silhouette moderado reflete isso.
- `vulnerabilidade_score` e `log_zeis` têm Spearman **0,96**: na prática o eixo dominante é ZEIS/área, não um perfil socioambiental completo.
- Sem população, "casos médios" mistura risco com tamanho populacional; a validação externa é indicativa.
- O `historico_score` do lookup é derivado de surtos e não deve entrar na clusterização sem revisão.
- k=3 é uma escolha condicionada aos dados atuais; não é uma verdade do território.
- Cluster ecológico de bairros; não vale para indivíduos.

## Fala de 15 min (roteiro)

1. Clusterizamos bairros com três proxies territoriais; casos ficam só para validar.
2. O silhouette sozinho sugere k=2, mas k=2 é instável no bootstrap (ARI mínimo 0,17).
3. k≥4 cria clusters menores que 10 bairros; com os critérios definidos, k=3 é o único admissível.
4. Os três perfis se diferenciam em casos (Kruskal p = 4,4 × 10⁻⁶), mas parcialmente por tamanho populacional.
5. O resultado é preliminar: volta para a S2 com IDH, densidade, intermitência e LST.

## Artefatos

- Notebook: [`backend/notebooks/sp5_clusters_k.ipynb`](../../backend/notebooks/sp5_clusters_k.ipynb)
- Dendrograma: [`sp5_dendrograma.png`](../../backend/notebooks/saidas/sp5_dendrograma.png)
- Silhouette por k + estabilidade: [`sp5_silhouette_por_k.png`](../../backend/notebooks/saidas/sp5_silhouette_por_k.png)
- Silhouette por bairro: [`sp5_silhouette_clusters.png`](../../backend/notebooks/saidas/sp5_silhouette_clusters.png)
- Mapa dos perfis: [`sp5_mapa_clusters.png`](../../backend/notebooks/saidas/sp5_mapa_clusters.png)
- Perfis: [`sp5_perfis_clusters.csv`](../../backend/notebooks/saidas/sp5_perfis_clusters.csv)
- Bairros × cluster: [`sp5_bairros_clusters.csv`](../../backend/notebooks/saidas/sp5_bairros_clusters.csv)
