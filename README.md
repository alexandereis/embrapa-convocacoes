# Painel de Convocações · Concurso EMBRAPA 2025

Dashboard estático que acompanha em tempo quase real as convocações e contratações
do concurso da EMBRAPA, com um **coletor de dados próprio** que recalcula todas as
métricas e publica um `data.json` versionado. Tudo automatizado via GitHub Actions.

```
embrapa-dashboard/
├── collector/                  # o coletor (Python puro, sem dependências)
│   ├── collect.py              # orquestrador: extrai → recalcula → grava data.json
│   ├── transform.py            # TODAS as métricas são calculadas aqui
│   ├── config.py               # qual fonte usar + parâmetros
│   └── extractors/             # adaptadores de fonte (plugáveis)
│       ├── base.py             # interface RawData
│       ├── upstream_repo.py    # adaptador ATIVO (fonte pública consolidada)
│       └── google_sheet.py.exemplo  # modelo p/ migrar para planilha própria
├── site/
│   ├── index.html              # o dashboard (lê ./data/data.json)
│   └── data/data.json          # gerado pelo coletor (commitado pelo Actions)
├── .github/workflows/coleta.yml# cron de hora em hora + deploy no Pages
└── run_local.sh                # rodar tudo localmente
```

## Como funciona

1. O **coletor** (`collect.py`) chama o adaptador de fonte ativo, que baixa os dados
   **brutos** (lista de convocados, resumo por opção e os eventos datados de
   convocação/contratação).
2. O **transform** recalcula do zero: totais por status e cargo, percentuais,
   desistências, séries semanais/mensais, velocidade diária com médias móveis,
   ranking de unidades, distribuição de opções e projeção de término. Nada vem
   "pronto" da fonte.
3. O resultado é gravado em `site/data/data.json`.
4. O **dashboard** carrega esse JSON (mesma origem, sem CORS) e renderiza tudo.
5. O **GitHub Actions** roda o coletor de hora em hora, commita o `data.json` se
   mudou e republica o site.

## Rodar localmente

Pré-requisito: Python 3.9+ (nenhuma biblioteca externa).

```bash
./run_local.sh
# ou manualmente:
python3 collector/collect.py          # gera site/data/data.json
cd site && python3 -m http.server 8000
# abra http://localhost:8000
```

> Não abra o `index.html` com duplo clique (`file://`): o navegador bloqueia a
> leitura do `data.json`. Use sempre um servidor local (o comando acima).

Validar sem gravar nada: `python3 collector/collect.py --check`

## Publicar online (GitHub Pages + Actions) — passo a passo

Esta é a opção recomendada: gratuita, sem servidor, e a automação já vem pronta.

1. **Crie um repositório** no GitHub (público) e suba esta pasta:
   ```bash
   cd embrapa-dashboard
   git init && git add . && git commit -m "feat: painel de convocacoes Embrapa"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/SEU_REPO.git
   git push -u origin main
   ```
2. **Ative o GitHub Pages por Actions**: repositório → *Settings* → *Pages* →
   em *Build and deployment* → *Source* = **GitHub Actions**.
3. **Permita que o Actions escreva no repo**: *Settings* → *Actions* → *General* →
   *Workflow permissions* → marque **Read and write permissions** → *Save*.
   (Necessário para o bot commitar o `data.json`.)
4. **Dispare o primeiro deploy**: aba *Actions* → workflow *Coleta e Deploy* →
   *Run workflow*. Ele coleta os dados, commita o `data.json` e publica.
5. Pronto. O site fica em `https://SEU_USUARIO.github.io/SEU_REPO/`.
   A partir daí, atualiza sozinho a cada hora (`cron` no workflow).

Para mudar a frequência, edite o `cron` em `.github/workflows/coleta.yml`
(ex.: `*/30 * * * *` = a cada 30 min).

### Domínio próprio (opcional)
Crie um arquivo `site/CNAME` com seu domínio (ex.: `convocacoes.seudominio.com.br`)
e aponte um registro CNAME no seu DNS para `SEU_USUARIO.github.io`.

## Trocar a fonte de dados

O adaptador ativo (`upstream_repo`) ingere a fonte pública consolidada que já
existe. Para tornar o painel 100% independente, crie seu próprio adaptador:

1. Copie `extractors/google_sheet.py.exemplo` para `extractors/google_sheet.py`.
2. Publique sua planilha como CSV (*Arquivo → Compartilhar → Publicar na web*)
   e cole as URLs no arquivo. Ajuste os nomes das colunas.
3. Registre o adaptador em `extractors/__init__.py`.
4. Em `config.py`, defina `EXTRACTOR = "google_sheet"`.

O `transform.py` e o site **não mudam**.

## Alternativas de hospedagem

| Opção | Custo | Automação | Observação |
|---|---|---|---|
| **GitHub Pages + Actions** | grátis | cron nativo | recomendado; tudo num repo |
| Cloudflare Pages + Cron Triggers | grátis | via Worker | ótimo desempenho/CDN |
| Netlify + Scheduled Functions | grátis (limites) | cron | simples, build automático |
| VPS + cron + Nginx | pago | cron do SO | mais controle, mais manutenção |

## Aviso

Painel **independente** de acompanhamento, baseado em dados públicos. Não é um
canal oficial da EMBRAPA. As projeções são estimativas estatísticas e não
representam compromisso do órgão. Dê sempre crédito à fonte usada (rodapé do site).
