// Cloudflare Worker — vigia o painel oficial (Looker) e dispara o GitHub
// Actions SO quando a fonte muda de verdade.
//
// Roda no Cron Trigger do Cloudflare (ex.: a cada 1 min). A checagem rapida
// acontece aqui (fora do GitHub), entao o Actions so executa/commita quando ha
// novidade real -> rapido E sem encher o historico de runs.
//
// Bindings/secrets esperados (ver worker/SETUP.md):
//   - KV namespace bind: WATCH_KV
//   - secret GH_TOKEN : Personal Access Token (classic, escopo "repo")
//   - var    GH_REPO  : "alexandereis/embrapa-convocacoes"

const ENDPOINT = "https://datastudio.google.com/embed/batchedDataV2";

// Replica da query da TABELA DE CONVOCADOS (mesma do coletor), pedindo todas
// as linhas de uma vez para a assinatura cobrir o maximo possivel.
const PAYLOAD = {"dataRequest":[{"requestContext":{"reportContext":{"reportId":"081070ee-89c7-4e57-85bc-04d4601aa513","pageId":"80063060","mode":1,"componentId":"cd-47x8z6vqwd","displayType":"simple-table"},"requestMode":0},"datasetSpec":{"dataset":[{"datasourceId":"71a5a632-8fb5-4044-ad33-6496c93fb112","revisionNumber":0,"parameterOverrides":[]}],"queryFields":[{"name":"qt_d","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_D_"}},{"name":"qt_e","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_E_"}},{"name":"qt_h","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_H_"}},{"name":"qt_q","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_Q_"}},{"name":"qt_j","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_J_"}},{"name":"qt_k","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_K_"}}],"sortData":[{"sortColumn":{"name":"qt_d","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_D_"}},"sortDir":0}],"includeRowsCount":true,"paginateInfo":{"startRow":1,"rowsCount":5000},"dsFilterOverrides":[],"filters":[{"filterDefinition":{"filterExpression":{"include":false,"conceptType":0,"concept":{"ns":"t0","name":"qt_fd"},"filterConditionType":"NU","stringValues":[""],"numberValues":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"_D_"}}}},"dataSubsetNs":{"datasetNs":"d0","tableNs":"t0","contextNs":"c0"},"version":3}],"features":[],"dateRanges":[],"contextNsCount":1,"calculatedField":[],"needGeocoding":false,"geoFieldMask":[],"multipleGeocodeFields":[],"timezone":"America/Sao_Paulo"},"role":"main","retryHints":{"useClientControlledRetry":true,"isLastRetry":false,"retryCount":0,"originalRequestId":"w_0_0"}}]};

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(checar(env));
  },
  // permite testar/forcar manualmente abrindo a URL do worker
  async fetch(req, env) {
    const r = await checar(env, true);
    return new Response(JSON.stringify(r), {headers: {"content-type": "application/json"}});
  },
};

async function checar(env, manual = false) {
  let texto;
  try {
    const resp = await fetch(ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://lookerstudio.google.com",
        "Referer": "https://lookerstudio.google.com/",
        "User-Agent": "Mozilla/5.0 embrapa-watcher",
      },
      body: JSON.stringify(PAYLOAD),
    });
    texto = await resp.text();
  } catch (e) {
    return {ok: false, erro: "fetch", detalhe: String(e)};
  }

  const sig = await assinatura(texto);
  if (!sig) return {ok: false, erro: "sem dados (formato inesperado)"};

  const anterior = await env.WATCH_KV.get("sig");
  // grava no KV SO quando muda (poupa o free tier: 1000 escritas/dia)
  if (anterior !== null && sig === anterior) return {ok: true, acao: "sem mudanca"};
  await env.WATCH_KV.put("sig", sig);
  if (anterior === null) return {ok: true, acao: "baseline gravado"};

  // mudou -> dispara o GitHub Actions
  const disp = await fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GH_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "embrapa-watcher",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({event_type: "fonte-mudou"}),
  });
  return {ok: true, acao: "MUDOU -> disparou Actions", github_status: disp.status};
}

function stripXSSI(t) {
  const i = t.indexOf("{");
  return i < 0 ? t : t.slice(i);
}

async function assinatura(texto) {
  let base;
  try {
    const data = JSON.parse(stripXSSI(texto));
    const tbl = data.dataResponse[0].dataSubset[0].dataset.tableDataset;
    const cols = tbl.column || [];
    base = "n=" + (tbl.totalCount || 0) + ";" + cols.map(c => {
      const v = (c.stringColumn && c.stringColumn.values) || [];
      const ni = c.nullIndex || [];
      return v.join("") + "#" + ni.join(",");
    }).join("");
  } catch (e) {
    return null;
  }
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(base));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
}
