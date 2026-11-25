import { usePulso } from "../context/PulsoContext";
import { PESOS_PRIORIZACAO } from "../data/priorizacao";
import BadgeClassificacao from "../components/BadgeClassificacao";

const NOMES_FEATURES = {
  tendenciaEpidemiologica: "Tendência epidemiológica",
  condicoesClimaticas: "Condições climáticas",
  focosIdentificados: "Focos identificados",
  vulnerabilidadeTerritorial: "Vulnerabilidade territorial",
  historico: "Histórico",
};

function formatarFatorValor(chave, valor) {
  if (chave === "tendenciaEpidemiologica") {
    const crescimento = valor >= 50 ? `+${((valor - 50) * 2).toFixed(0)}%` : `${((valor - 50) * 2).toFixed(0)}%`;
    return { valor: crescimento, descricao: "Aumento das notificações em relação ao período anterior." };
  }
  if (chave === "condicoesClimaticas") {
    return { valor: `+${valor.toFixed(0)}%`, descricao: "Chuva acumulada acima da média histórica do período." };
  }
  if (chave === "focosIdentificados") {
    return { valor: `+${valor.toFixed(0)}%`, descricao: "Crescimento recente dos focos registrados." };
  }
  if (chave === "vulnerabilidadeTerritorial") {
    const nivel = valor >= 70 ? "Alta" : valor >= 40 ? "Média" : "Baixa";
    return { valor: nivel, descricao: "Presença de fatores territoriais associados à maior exposição." };
  }
  return { valor: "Padrão", descricao: "Períodos anteriores com sinais similares apresentaram agravamento posterior." };
}

// Evolução simulada das últimas semanas
const EVOLUCAO_MOCK = [
  { semana: "Atual - 3", alerta: "Estável", classe: "evolucao-tabela__alerta--estavel" },
  { semana: "Atual - 2", alerta: "Atenção", classe: "evolucao-tabela__alerta--atencao" },
  { semana: "Atual - 1", alerta: "Alto", classe: "evolucao-tabela__alerta--alto" },
  { semana: "Atual", alerta: "Crítico", classe: "evolucao-tabela__alerta--critico" },
];

export default function TelaExplicacao() {
  const { territoriosOrdenados, territorioSelecionado, irPara, idhReferencia } = usePulso();
  const territorio =
    territoriosOrdenados.find((t) => t.nome?.toUpperCase() === territorioSelecionado?.toUpperCase()) ??
    territoriosOrdenados[0];

  if (!territorio) return null;

  const idhAno = idhReferencia?.ano ?? 2010;
  const defasagemAnos = Math.max(0, new Date().getFullYear() - idhAno);

  const componentes = [
    { chave: "tendenciaEpidemiologica", valor: territorio.tendenciaEpidemiologica },
    { chave: "condicoesClimaticas", valor: territorio.condicoesClimaticas },
    { chave: "focosIdentificados", valor: territorio.focosIdentificados },
    { chave: "vulnerabilidadeTerritorial", valor: territorio.vulnerabilidadeTerritorial },
    { chave: "historico", valor: territorio.historico },
  ];

  const contribuicoes = componentes.map((c) => ({
    ...c,
    label: NOMES_FEATURES[c.chave],
    contribuicao: c.valor * PESOS_PRIORIZACAO[c.chave],
    percentual: PESOS_PRIORIZACAO[c.chave] * 100,
  }));

  const maxContrib = Math.max(...contribuicoes.map((c) => c.contribuicao)) || 1;

  return (
    <div className="tela">
      {/* Breadcrumb */}
      <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 4 }}>
        Prioridades / {territorio.nome}
      </div>

      {/* Cabeçalho */}
      <div className="card explicacao-cabecalho">
        <div className="explicacao-cabecalho__left">
          <div style={{ fontSize: 20, fontWeight: 700 }}>
            {territorio.nome} — Prioridade {territorio.score}/100
          </div>
        </div>
        <div className="explicacao__badges">
          <BadgeClassificacao classificacao={territorio.classificacao} />
          <span className="badge-confianca">Confiança da análise: Alta</span>
        </div>
      </div>

      {/* Intro */}
      <div className="card explicacao-intro">
        <div className="explicacao-intro__titulo">
          Por que este território é prioritário?
        </div>
        <div className="explicacao-intro__texto">
          A combinação de crescimento das notificações, chuva acumulada acima da
          média e aumento de focos identificados elevou a prioridade de
          intervenção no território.
        </div>
      </div>

      {/* Fatores identificados (5 cards) */}
      <div className="fatores-grid">
        {componentes.map((c) => {
          const formatado = formatarFatorValor(c.chave, c.valor);
          return (
            <div key={c.chave} className="card fator-card">
              <div className="fator-card__nome">{NOMES_FEATURES[c.chave]}</div>
              <div className={`fator-card__valor ${c.valor >= 70 ? "fator-card__valor--critico" : c.valor >= 50 ? "fator-card__valor--alto" : ""}`}>
                {formatado.valor}
              </div>
              <div className="fator-card__descricao">{formatado.descricao}</div>
            </div>
          );
        })}
      </div>

      {/* Contexto socioterritorial — referência, não componente do score */}
      {territorio.idh != null && (
        <div className="card contexto-idh">
          <div className="contexto-idh__topo">
            <div>
              <div className="contexto-idh__titulo">IDH do bairro — Atlas Brasil</div>
              <div className="contexto-idh__fonte">
                {territorio.idhUdhCount > 0 &&
                  `${territorio.idhUdhCount} ${territorio.idhUdhCount === 1 ? "UDH" : "UDHs"} · `}
                Censo {idhAno} · defasagem de {defasagemAnos} anos
              </div>
            </div>
            <span className="contexto-idh__badge">Contexto — não entra no score</span>
          </div>
          <div className="contexto-idh__valor">{territorio.idh.toFixed(3)}</div>
          <p className="contexto-idh__descricao">
            IDHM das Unidades de Desenvolvimento Humano (UDHs) que compõem o
            bairro, ponderado pela população. É um retrato do Censo {idhAno}; serve
            para analisar associação com a incidência, não para medir a condição atual.
          </p>
        </div>
      )}

      {/* Barras de contribuição + Evolução */}
      <div className="visao-geral__grid">
        <div className="card contribuicoes-card">
          <div className="contribuicoes-card__titulo">
            Fatores que influenciaram a prioridade
          </div>
          {contribuicoes.map((c) => (
            <div key={c.chave} className="contribuicao-barra-figma">
              <span className="contribuicao-barra-figma__label">{c.label}</span>
              <div className="contribuicao-barra-figma__track">
                <div
                  className="contribuicao-barra-figma__fill"
                  style={{ width: `${(c.contribuicao / maxContrib) * 100}%` }}
                />
              </div>
              <span className="contribuicao-barra-figma__percent">
                {c.percentual.toFixed(0)}%
              </span>
            </div>
          ))}
          <div className="nota-metodologica">
            Os percentuais representam a contribuição dos grupos de sinais para a
            priorização atual e não uma relação individual de causalidade.
          </div>
        </div>

        <div className="card evolucao-card">
          <div className="evolucao-card__titulo">Evolução dos sinais</div>
          <table className="evolucao-tabela">
            <thead>
              <tr>
                <th>Semana</th>
                <th>Alerta</th>
              </tr>
            </thead>
            <tbody>
              {EVOLUCAO_MOCK.map((e) => (
                <tr key={e.semana}>
                  <td>{e.semana}</td>
                  <td className={e.classe}>{e.alerta}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <button
        className="btn btn--primary"
        style={{ alignSelf: "flex-start" }}
        onClick={() => irPara("recomendacao", territorio.nome)}
      >
        Ver ação recomendada
      </button>
    </div>
  );
}
