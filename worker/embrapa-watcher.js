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

// De quanto em quanto tempo conferir se o PAINEL ficou para tras da fonte.
// So vale quando a assinatura nao mudou, entao isso nao atrasa nenhuma novidade
// -- e apenas a rede de seguranca, e nao pode martelar o Actions a cada minuto.
const INTERVALO_CONFERE_MS = 10 * 60 * 1000;

// Versao do arquivo, devolvida em toda resposta. O deploy do Worker e manual
// (copiar e colar no painel da Cloudflare), entao sem isso nao ha como saber se
// o que esta no ar e o que esta no repositorio. Suba ao mudar este arquivo.
const VERSAO = "2026-09-11.2";

export default {
  async scheduled(event, env, ctx) {
    // loga o resultado de cada execucao do cron (visivel nos Real-time Logs).
    ctx.waitUntil(checar(env).then((r) => console.log("[cron]", JSON.stringify(r))));
  },
  async fetch(req, env) {
    const r = await checar(env, true);
    return new Response(JSON.stringify(r), {headers: {"content-type": "application/json"}});
  },
};

/** URL do data.json publicado, derivada do proprio GH_REPO (sem config nova). */
export function painelUrl(ghRepo) {
  const [dono, repo] = String(ghRepo || "").split("/");
  return `https://${dono}.github.io/${repo}/data/data.json`;
}

/** Le o total de convocados do data.json SEM parsear os 300 KB inteiros.
 *  O campo fica nos primeiros bytes do arquivo, entao um regex resolve. */
export function convocadosNoTexto(texto) {
  const m = String(texto).match(/"total_convocados":(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

/** Quantos convocados o painel PUBLICADO declara (null se nao der para saber). */
async function convocadosPublicados(env) {
  const url = painelUrl(env.GH_REPO) + "?cb=" + Date.now();
  try {
    const resp = await fetch(url, {
      headers: {"Range": "bytes=0-4095", "Cache-Control": "no-cache"},
    });
    return convocadosNoTexto(await resp.text());
  } catch (e) {
    return null;
  }
}

function stripXSSI(t) {
  const i = t.indexOf("{");
  return i < 0 ? t : t.slice(i);
}

async function sha256(s) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
}

/** Dispara o repository_dispatch. Devolve {ok, status, corpo}. */
async function dispararActions(env) {
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
  const corpo = await disp.text().catch(() => "");
  return {ok: disp.status >= 200 && disp.status < 300, status: disp.status, corpo};
}

/**
 * Rede de seguranca: a assinatura da fonte nao mudou, mas o PAINEL pode ter
 * ficado para tras -- a coleta anterior pode ter sido descartada (o runner do
 * Actions as vezes recebe uma geracao antiga da fonte). Como a assinatura nova
 * ja esta gravada, aquela mudanca nunca mais dispararia sozinha.
 *
 * Cutuca o Actions enquanto o painel estiver menor que a fonte, no maximo uma
 * vez a cada INTERVALO_CONFERE_MS. NAO mexe na assinatura: ela ja reflete a
 * fonte; o que esta atrasado e a publicacao.
 */
async function conferirAtraso(env, totalFonte) {
  const agora = Date.now();
  const ultima = parseInt(await env.WATCH_KV.get("ultima_conferida") || "0", 10);
  if (agora - ultima < INTERVALO_CONFERE_MS) return null;
  await env.WATCH_KV.put("ultima_conferida", agora);

  const publicados = await convocadosPublicados(env);
  // Painel igual ou MAIOR que a fonte nao e atraso: a fonte tambem serve
  // geracao antiga, e cutucar so faria o Actions descartar a coleta.
  if (publicados === null || !totalFonte || publicados >= totalFonte) return null;

  const disp = await dispararActions(env);
  if (!disp.ok) {
    return {ok: false, erro: "painel atrasado, mas o disparo falhou",
            github_status: disp.status, publicados, total: totalFonte, versao: VERSAO};
  }
  return {ok: true, acao: "painel atrasado -> cutucou o Actions",
          publicados, total: totalFonte, versao: VERSAO};
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
    return {ok: false, erro: "fetch", detalhe: String(e), versao: VERSAO};
  }

  // interpreta a resposta
  let tbl;
  try {
    const data = JSON.parse(stripXSSI(texto));
    const dr = (data.dataResponse || [])[0] || {};
    if (dr.errorStatus) {
      return {ok: false, erro: "Looker recusou", motivo: dr.errorStatus.reasonStr,
              categoria: dr.errorStatus.errorCategoryStr, versao: VERSAO};
    }
    tbl = (((dr.dataSubset || [])[0] || {}).dataset || {}).tableDataset;
  } catch (e) {
    return {ok: false, erro: "json", trecho: texto.slice(0, 160), versao: VERSAO};
  }
  if (!tbl || !tbl.column) {
    return {ok: false, erro: "sem tableDataset", trecho: texto.slice(0, 160), versao: VERSAO};
  }

  const base = "n=" + (tbl.totalCount || 0) + ";" + tbl.column.map(c => {
    const v = (c.stringColumn && c.stringColumn.values) || [];
    return v.join("") + "#" + (c.nullIndex || []).join(",");
  }).join("");
  const sig = await sha256(base);

  // ---- geracao antiga? -----------------------------------------------------
  // A tabela de convocados so cresce, entao uma leitura MENOR que o maior total
  // ja visto e cache velho da fonte. Nao dispara e -- importante -- nao avanca a
  // assinatura: se avancasse, a volta para a geracao nova pareceria "mudanca" e
  // dispararia de novo. Era esse pingue-pongue que enchia o Actions de runs que
  // sempre terminavam com a coleta descartada.
  // Se a fonte encolher DE VERDADE, o cron de 6h do Actions continua rodando e a
  // decisao fica com o coletor (EMBRAPA_ACEITA_ENCOLHIMENTO), nao aqui.
  const pico = parseInt(await env.WATCH_KV.get("pico") || "0", 10);
  const total = tbl.totalCount || 0;
  if (pico && total && total < pico) {
    return {ok: true, acao: "geracao antiga da fonte -> ignorada",
            total, pico, versao: VERSAO};
  }
  if (total > pico) await env.WATCH_KV.put("pico", total);

  const anterior = await env.WATCH_KV.get("sig");
  if (anterior !== null && sig === anterior) {
    // A fonte nao mudou -- mas o painel pode nao ter publicado a ultima vez.
    const atraso = await conferirAtraso(env, tbl.totalCount);
    if (atraso) return atraso;
    return {ok: true, acao: "sem mudanca", total: tbl.totalCount, versao: VERSAO};
  }
  // 1a vez (sem baseline): so grava o ponto de partida, sem disparar nada.
  if (anterior === null) {
    await env.WATCH_KV.put("sig", sig);
    return {ok: true, acao: "baseline gravado", total: tbl.totalCount, versao: VERSAO};
  }

  // Houve mudanca: dispara o Actions PRIMEIRO. So avancamos a assinatura no KV
  // se o disparo REALMENTE der certo (2xx). Se falhar (token errado/expirado,
  // repo errado, sem escopo), NAO gravamos -> no minuto seguinte tenta de novo
  // (auto-cura), em vez de "engolir" a mudanca silenciosamente.
  let disp;
  try {
    disp = await dispararActions(env);
  } catch (e) {
    return {ok: false, erro: "github fetch", detalhe: String(e), total: tbl.totalCount, versao: VERSAO};
  }
  if (disp.ok) {
    await env.WATCH_KV.put("sig", sig);   // so avanca o ponteiro se disparou de fato
    return {ok: true, acao: "MUDOU -> disparou Actions",
            github_status: disp.status, total: tbl.totalCount, versao: VERSAO};
  }
  // disparo recusado: assinatura NAO gravada (vai retentar) + mostra o motivo.
  return {ok: false, erro: "github dispatch falhou (assinatura NAO gravada, vai retentar)",
          github_status: disp.status, corpo: disp.corpo.slice(0, 200), total: tbl.totalCount,
          versao: VERSAO};
}

export { checar };
