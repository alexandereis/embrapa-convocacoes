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

// Query REGISTRADA da tabela de convocados (identica a do painel — campos,
// ordenacao e filtros EXATOS; so a paginacao muda). Anonimo so aceita a query
// registrada, por isso ela tem que ser igual a original.
const PAYLOAD = {"dataRequest":[{"requestContext":{"reportContext":{"reportId":"081070ee-89c7-4e57-85bc-04d4601aa513","pageId":"80063060","mode":1,"componentId":"cd-47x8z6vqwd","displayType":"simple-table"},"requestMode":0},"datasetSpec":{"dataset":[{"datasourceId":"71a5a632-8fb5-4044-ad33-6496c93fb112","revisionNumber":0,"parameterOverrides":[]}],"queryFields":[{"name":"qt_1pxv074twd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_D_"}},{"name":"qt_otdav44twd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_E_"}},{"name":"qt_nc73k64twd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_H_"}},{"name":"qt_5go3364twd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_Q_"}},{"name":"qt_duqvbfyxyd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_J_"}},{"name":"qt_ge9totyxyd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_K_"}}],"sortData":[{"sortColumn":{"name":"qt_1pxv074twd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_D_"}},"sortDir":0},{"sortColumn":{"name":"qt_rfmzqsixwd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_C_","aggregation":6}},"sortDir":0}],"includeRowsCount":true,"relatedDimensionMask":{"addDisplay":false,"addUniqueId":false,"addLatLong":false},"paginateInfo":{"startRow":1,"rowsCount":2000},"dsFilterOverrides":[],"filters":[{"filterDefinition":{"filterExpression":{"include":false,"conceptType":0,"concept":{"ns":"t0","name":"qt_1s3l3awqwd"},"filterConditionType":"NU","stringValues":[],"numberValues":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"_A_","aggregation":0}}}},"dataSubsetNs":{"datasetNs":"d0","tableNs":"t0","contextNs":"c0"},"version":3},{"filterDefinition":{"filterExpression":{"include":false,"conceptType":0,"concept":{"ns":"t0","name":"qt_apxykcxqwd"},"filterConditionType":"NU","stringValues":[],"numberValues":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"_G_","aggregation":0}}}},"dataSubsetNs":{"datasetNs":"d0","tableNs":"t0","contextNs":"c0"},"version":3},{"filterDefinition":{"filterExpression":{"include":false,"conceptType":0,"concept":{"ns":"t0","name":"qt_4y2av84twd"},"filterConditionType":"NU","stringValues":[""],"numberValues":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"_D_"}}}},"dataSubsetNs":{"datasetNs":"d0","tableNs":"t0","contextNs":"c0"},"version":3}],"features":[],"dateRanges":[],"contextNsCount":1,"calculatedField":[],"needGeocoding":false,"geoFieldMask":[],"multipleGeocodeFields":[],"timezone":"America/Sao_Paulo"},"role":"main","retryHints":{"useClientControlledRetry":true,"isLastRetry":false,"retryCount":0,"originalRequestId":"cd-47x8z6vqwd_0_0"}}]};

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(checar(env));
  },
  async fetch(req, env) {
    const r = await checar(env, true);
    return new Response(JSON.stringify(r), {headers: {"content-type": "application/json"}});
  },
};

function stripXSSI(t) {
  const i = t.indexOf("{");
  return i < 0 ? t : t.slice(i);
}

async function sha256(s) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
}

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

  // interpreta a resposta
  let tbl;
  try {
    const data = JSON.parse(stripXSSI(texto));
    const dr = (data.dataResponse || [])[0] || {};
    if (dr.errorStatus) {
      return {ok: false, erro: "Looker recusou", motivo: dr.errorStatus.reasonStr,
              categoria: dr.errorStatus.errorCategoryStr};
    }
    tbl = (((dr.dataSubset || [])[0] || {}).dataset || {}).tableDataset;
  } catch (e) {
    return {ok: false, erro: "json", trecho: texto.slice(0, 160)};
  }
  if (!tbl || !tbl.column) {
    return {ok: false, erro: "sem tableDataset", trecho: texto.slice(0, 160)};
  }

  const base = "n=" + (tbl.totalCount || 0) + ";" + tbl.column.map(c => {
    const v = (c.stringColumn && c.stringColumn.values) || [];
    return v.join("") + "#" + (c.nullIndex || []).join(",");
  }).join("");
  const sig = await sha256(base);

  const anterior = await env.WATCH_KV.get("sig");
  if (anterior !== null && sig === anterior) {
    return {ok: true, acao: "sem mudanca", total: tbl.totalCount};
  }
  await env.WATCH_KV.put("sig", sig);  // grava SO quando muda (poupa o free tier)
  if (anterior === null) {
    return {ok: true, acao: "baseline gravado", total: tbl.totalCount};
  }

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
  return {ok: true, acao: "MUDOU -> disparou Actions", github_status: disp.status, total: tbl.totalCount};
}
