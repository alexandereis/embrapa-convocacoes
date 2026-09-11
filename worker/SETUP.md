# Vigia rápido (Cloudflare Worker) — atualização quase em tempo real

Este Worker fica lendo o painel oficial (Looker) **a cada 1 minuto** e dispara o
GitHub Actions **só quando a fonte muda de verdade**. Assim o dashboard atualiza
em ~1–2 min após qualquer mudança, e o histórico de *Actions* fica limpo (só roda
quando há novidade real). Tudo em planos **gratuitos**.

## Passo 1 — Token do GitHub (para o Worker acionar o robô)

1. GitHub → foto → *Settings* → *Developer settings* → *Personal access tokens* →
   *Tokens (classic)* → **Generate new token (classic)**.
2. Nome: `embrapa-worker`. Validade: a que preferir. Marque o escopo **`repo`**.
3. **Generate token** e copie (só aparece uma vez).

## Passo 2 — Cria o Worker no Cloudflare

1. Crie conta grátis em https://dash.cloudflare.com → menu **Workers & Pages** →
   **Create** → **Create Worker** → dê o nome `embrapa-watcher` → **Deploy**.
2. Clique em **Edit code**, apague o conteúdo e **cole todo o `embrapa-watcher.js`**
   (o arquivo desta pasta) → **Deploy**.

## Passo 3 — KV (memória do Worker)

1. **Workers & Pages** → **KV** → **Create a namespace** → nome `embrapa-sig`.
2. Volte no Worker → aba **Settings** → **Bindings** → **Add** → **KV namespace**:
   - *Variable name*: `WATCH_KV`
   - *KV namespace*: `embrapa-sig` → **Save**.

## Passo 4 — Variáveis e segredo

No Worker → **Settings** → **Variables and Secrets**:

- **Add variable** (texto normal): nome `GH_REPO`, valor `alexandereis/embrapa-convocacoes`.
- **Add secret** (criptografado): nome `GH_TOKEN`, valor = o token do Passo 1.
- **Save / Deploy**.

## Passo 5 — Agendamento (a cada 1 minuto)

No Worker → **Settings** → **Triggers** (ou *Cron Triggers*) → **Add Cron Trigger** →
expressão `* * * * *` (a cada minuto) → **Add**.

## Passo 6 — Testar

- Abra a URL pública do Worker (algo como
  `https://embrapa-watcher.SEU-SUBDOMINIO.workers.dev`). Na 1ª vez deve responder
  `{"ok":true,"acao":"baseline gravado"}`; nas próximas, `"sem mudanca"`.
- Quando a fonte mudar de verdade, ele responde `"MUDOU -> disparou Actions"` e o
  workflow *Coleta e Deploy* roda sozinho (veja na aba **Actions** do repo).

## Como fica

- **Worker (a cada 1 min):** lê o Looker, compara; nada acontece se não mudou.
- **Só quando muda:** dispara o `repository_dispatch` → o robô coleta, recalcula e
  publica. O `collect.py` já só commita quando há mudança real.
- **Se o painel ficar para trás:** a cada 10 min o Worker compara o total de
  convocados da fonte com o do `data.json` já publicado. Se o painel estiver
  menor, ele cutuca o Actions de novo — sem mexer na assinatura. Isso existe
  porque a coleta pode ser **descartada**: o runner do Actions às vezes recebe
  uma geração antiga da fonte. Como a assinatura nova já teria sido gravada no
  disparo anterior, aquela mudança nunca mais dispararia sozinha e o painel só
  se recuperaria no cron de 6 h.
- **Rede de segurança:** o workflow ainda roda 4×/dia (cron) caso o Worker caia.

## Atualizando o Worker

Ao mudar o `embrapa-watcher.js`, repita o **Passo 2.2**: *Edit code*, apague
tudo, cole o arquivo novo e **Deploy**. Nada além do código muda — os bindings,
variáveis e o cron continuam como estão.

Para confirmar que o *Deploy* pegou o arquivo certo, abra a URL do Worker: toda
resposta traz `"versao"`, que deve bater com a constante `VERSAO` no topo do
`embrapa-watcher.js`. Sem isso não há como saber se o que está no ar é o que
está no repositório.

Os testes do Worker rodam localmente com `node --test` dentro de `worker/`, e
também no CI a cada push.

> O Worker faz ~1.440 leituras/dia (dentro do free tier). No KV ele grava
> quando a fonte muda, mais uma marca a cada 10 min da conferência de atraso —
> cerca de 150 a 200 escritas/dia, bem abaixo do limite de 1.000/dia.
