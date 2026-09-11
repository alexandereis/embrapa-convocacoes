// Testes do vigia -- rodam com `node --test` dentro de worker/.
//
// Cobrem o buraco descoberto em 11/09/2026: o vigia grava a assinatura nova
// assim que DISPARA o Actions, nao quando o painel realmente publica. Se a
// coleta for descartada (o runner do Actions recebe uma geracao antiga da
// fonte), ninguem cutuca de novo -- a mesma mudanca nunca mais dispara e o
// painel so se recupera no cron de 6h.
import assert from "node:assert/strict";
import test from "node:test";

import worker, { checar, painelUrl, convocadosNoTexto } from "./embrapa-watcher.js";

const REPO = "alexandereis/embrapa-convocacoes";

function kvFalso(inicial = {}) {
  const dados = new Map(Object.entries(inicial));
  return {
    get: async (k) => (dados.has(k) ? dados.get(k) : null),
    put: async (k, v) => void dados.set(k, String(v)),
    _dados: dados,
  };
}

/** Resposta do Looker com `total` linhas (uma coluna basta para a assinatura). */
function respostaLooker(total, marcador = "x") {
  const values = Array.from({ length: total }, (_, i) => marcador + i);
  return ")]}'\n" + JSON.stringify({
    dataResponse: [{
      dataSubset: [{
        dataset: { tableDataset: { totalCount: total, column: [{ stringColumn: { values } }] } },
      }],
    }],
  });
}

/**
 * Substitui o fetch global. Devolve o registro das chamadas.
 * `painelConvocados`: quantos convocados o data.json publicado declara.
 */
function fetchFalso({ total, painelConvocados, dispatchStatus = 204 }) {
  const chamadas = { looker: 0, painel: 0, dispatch: 0 };
  globalThis.fetch = async (url, opts = {}) => {
    const u = String(url);
    if (u.includes("batchedDataV2")) {
      chamadas.looker++;
      return new Response(respostaLooker(total));
    }
    if (u.includes("data.json")) {
      chamadas.painel++;
      return new Response(`{"general":{"total_convocados":${painelConvocados}}}`);
    }
    if (u.includes("api.github.com")) {
      chamadas.dispatch++;
      chamadas.ultimoCorpo = opts.body;
      return new Response(null, { status: dispatchStatus });
    }
    throw new Error("URL inesperada no teste: " + u);
  };
  return chamadas;
}

function env(kv) {
  return { WATCH_KV: kv, GH_REPO: REPO, GH_TOKEN: "t0ken" };
}

test("painelUrl deriva a URL publicada a partir do GH_REPO", () => {
  assert.equal(
    painelUrl(REPO),
    "https://alexandereis.github.io/embrapa-convocacoes/data/data.json",
  );
});

test("convocadosNoTexto acha o total sem parsear o JSON inteiro", () => {
  assert.equal(convocadosNoTexto('{"general":{"total_convocados":1169,"x":1}'), 1169);
  assert.equal(convocadosNoTexto("{sem o campo}"), null);
});

test("fonte mudou: dispara e avanca a assinatura", async () => {
  const kv = kvFalso({ sig: "assinatura-velha" });
  const chamadas = fetchFalso({ total: 1169, painelConvocados: 1157 });
  const r = await checar(env(kv));
  assert.equal(chamadas.dispatch, 1);
  assert.match(r.acao, /MUDOU/);
  assert.notEqual(await kv.get("sig"), "assinatura-velha");
});

test("nada mudou e o painel esta em dia: nao dispara nada", async () => {
  const kv = kvFalso();
  fetchFalso({ total: 1169, painelConvocados: 1169 });
  await checar(env(kv));                      // baseline
  const chamadas = fetchFalso({ total: 1169, painelConvocados: 1169 });
  const r = await checar(env(kv));
  assert.equal(chamadas.dispatch, 0);
  assert.equal(r.acao, "sem mudanca");
});

test("painel atrasado sem mudanca de assinatura: cutuca o Actions", async () => {
  // O cenario real: a coleta foi descartada, o painel ficou para tras e a
  // assinatura da fonte ja e a nova -- sem isso, ninguem dispara nunca mais.
  const kv = kvFalso();
  fetchFalso({ total: 1169, painelConvocados: 1169 });
  await checar(env(kv));                      // baseline com a fonte em 1169
  const chamadas = fetchFalso({ total: 1169, painelConvocados: 1157 });
  const r = await checar(env(kv));
  assert.equal(chamadas.dispatch, 1, "deveria cutucar o Actions");
  assert.match(r.acao, /atrasado/i);
});

test("a cutucada NAO mexe na assinatura da fonte", async () => {
  const kv = kvFalso();
  fetchFalso({ total: 1169, painelConvocados: 1169 });
  await checar(env(kv));
  const sigDepoisDoBaseline = await kv.get("sig");
  fetchFalso({ total: 1169, painelConvocados: 1157 });
  await checar(env(kv));
  assert.equal(await kv.get("sig"), sigDepoisDoBaseline);
});

test("nao cutuca duas vezes seguidas: respeita o intervalo", async () => {
  const kv = kvFalso();
  fetchFalso({ total: 1169, painelConvocados: 1169 });
  await checar(env(kv));
  fetchFalso({ total: 1169, painelConvocados: 1157 });
  await checar(env(kv));                      // 1a cutucada
  const chamadas = fetchFalso({ total: 1169, painelConvocados: 1157 });
  const r = await checar(env(kv));            // logo em seguida
  assert.equal(chamadas.dispatch, 0, "nao pode martelar o Actions a cada minuto");
  assert.equal(r.acao, "sem mudanca");
});

test("painel a frente da fonte nao e considerado atraso", async () => {
  // A fonte serve geracao antiga ao vigia tambem. Com a assinatura estavel e o
  // painel MAIOR que a fonte, cutucar so faria o Actions descartar a coleta.
  const kv = kvFalso();
  fetchFalso({ total: 1157, painelConvocados: 1169 });
  await checar(env(kv));                      // baseline: fonte velha em 1157
  const chamadas = fetchFalso({ total: 1157, painelConvocados: 1169 });
  const r = await checar(env(kv));
  assert.equal(chamadas.dispatch, 0);
  assert.ok(!/atrasado/i.test(r.acao || ""));
});

test("leitura menor que o pico conhecido e geracao antiga: nao dispara", async () => {
  // Sem isto o vigia entra em pingue-pongue: a fonte alterna entre a geracao
  // nova e uma antiga, cada alternancia muda a assinatura e cada mudanca vira
  // um run do Actions -- que sempre descarta a coleta. Puro desperdicio.
  const kv = kvFalso();
  fetchFalso({ total: 1169, painelConvocados: 1169 });
  await checar(env(kv));                      // baseline: pico 1169
  const chamadas = fetchFalso({ total: 1157, painelConvocados: 1169 });
  const r = await checar(env(kv));
  assert.equal(chamadas.dispatch, 0, "geracao antiga nao pode disparar o Actions");
  assert.match(r.acao, /antiga/i);
});

test("geracao antiga NAO avanca a assinatura", async () => {
  // Se avancasse, a volta para a geracao nova pareceria "mudanca" e dispararia
  // de novo -- o pingue-pongue continuaria pelo outro lado.
  const kv = kvFalso();
  fetchFalso({ total: 1169, painelConvocados: 1169 });
  await checar(env(kv));
  const sigDoPico = await kv.get("sig");
  fetchFalso({ total: 1157, painelConvocados: 1169 });
  await checar(env(kv));
  assert.equal(await kv.get("sig"), sigDoPico);
});

test("voltar para a geracao nova depois de uma antiga nao gera disparo", async () => {
  const kv = kvFalso();
  fetchFalso({ total: 1169, painelConvocados: 1169 });
  await checar(env(kv));                      // baseline
  fetchFalso({ total: 1157, painelConvocados: 1169 });
  await checar(env(kv));                      // oscilou para a antiga
  const chamadas = fetchFalso({ total: 1169, painelConvocados: 1169 });
  await checar(env(kv));                      // e voltou
  assert.equal(chamadas.dispatch, 0, "a volta ao normal nao e novidade");
});

test("conjunto que cresce dispara normalmente e move o pico", async () => {
  const kv = kvFalso();
  fetchFalso({ total: 1169, painelConvocados: 1169 });
  await checar(env(kv));
  const chamadas = fetchFalso({ total: 1180, painelConvocados: 1169 });
  const r = await checar(env(kv));
  assert.equal(chamadas.dispatch, 1);
  assert.match(r.acao, /MUDOU/);
  assert.equal(await kv.get("pico"), "1180");
});

test("mesmo total com conteudo diferente ainda e mudanca real", async () => {
  // Uma pessoa mudando de status nao altera a contagem -- e a novidade mais
  // comum do painel. A guarda de pico nao pode engolir isso.
  const kv = kvFalso();
  fetchFalso({ total: 1169, painelConvocados: 1169 });
  await checar(env(kv));
  const chamadas = { dispatch: 0 };
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u.includes("batchedDataV2")) return new Response(respostaLooker(1169, "y"));
    if (u.includes("data.json")) return new Response('{"general":{"total_convocados":1169}}');
    chamadas.dispatch++;
    return new Response(null, { status: 204 });
  };
  const r = await checar(env(kv));
  assert.equal(chamadas.dispatch, 1, "mudanca de status tem que disparar");
  assert.match(r.acao, /MUDOU/);
});

test("a resposta diz qual versao do vigia esta no ar", async () => {
  const kv = kvFalso();
  fetchFalso({ total: 1169, painelConvocados: 1169 });
  const r = await checar(env(kv));
  assert.ok(r.versao, "sem isso nao da para saber se o Deploy pegou o arquivo novo");
});

test("o handler do cron continua exportado", () => {
  assert.equal(typeof worker.scheduled, "function");
  assert.equal(typeof worker.fetch, "function");
});
