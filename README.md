# Painel de Convocações · Concurso EMBRAPA 2025

Dashboard estático que acompanha em tempo quase real as convocações e contratações
do concurso da EMBRAPA. A fonte é o **painel oficial da EMBRAPA** (Looker Studio):
o coletor replica a consulta pública do painel, **recalcula todas as métricas do
zero** e publica um `data.json` versionado. Tudo automatizado via GitHub Actions.

```
embrapa-dashboard/
├── collector/                  # o coletor (Python puro, sem dependências)
│   ├── collect.py              # orquestrador: extrai → recalcula → grava data.json
│   ├── transform.py            # TODAS as métricas são calculadas aqui
│   ├── timeline.py             # série temporal própria (seed + acúmulo)
│   ├── config.py               # qual fonte usar + parâmetros
│   ├── build_catalog.py        # (1x) gera o catálogo opção→cargo/vagas
│   ├── seed_history.py         # (1x) semeia a curva histórica da timeline
│   ├── data/catalog_opcoes.csv # catálogo de edital (versionado)
│   └── extractors/             # adaptadores de fonte (plugáveis)
│       ├── base.py             # interface RawData
│       ├── looker_studio.py    # adaptador ATIVO (painel OFICIAL, batchedDataV2)
│       ├── upstream_repo.py    # adaptador alternativo (fonte da comunidade)
│       └── google_sheet.py.exemplo  # modelo p/ planilha própria
├── site/
│   ├── index.html              # o dashboard (lê ./data/data.json)
│   └── data/
│       ├── data.json           # gerado pelo coletor (commitado pelo Actions)
│       ├── timeline_seed.json  # curva histórica semeada (1x)
│       └── timeline_state.json # snapshots acumulados pelo coletor
├── .github/workflows/coleta.yml# cron de hora em hora + deploy no Pages
└── run_local.sh                # rodar tudo localmente
```

## Como funciona

1. O **coletor** (`collect.py`) chama o adaptador `looker_studio`, que replica a
   consulta `batchedDataV2` do painel oficial (acesso anônimo) e pagina **todas**
   as ~1045 pessoas: colocação/cota, nome, opção, status, unidade e cidade.
2. O resumo **por opção/cargo** é **recalculado** a partir dos status oficiais,
   cruzado com o catálogo estático opção→cargo/área/subárea/vagas (`build_catalog.py`,
   dado de edital, versionado).
3. A **linha do tempo** é própria (`timeline.py`): a curva histórica é semeada uma
   vez (`seed_history.py`) e, a cada coleta, só quem é novo/mudou de status gera um
   evento datado — sem depender de datas do oficial (que não as expõe).
4. O **transform** recalcula tudo: totais por status/cargo/cota, percentuais,
   desistências, séries semanais/mensais, velocidade, ranking de unidades, projeção.
5. O resultado vai para `site/data/data.json`; o **dashboard** lê esse JSON.
6. O **GitHub Actions** roda de hora em hora, commita `data.json` + `timeline_state.json`
   e republica o site.

## Primeira configuração (uma vez)

Antes da primeira coleta, gere o catálogo e semeie o histórico:

```bash
python3 collector/build_catalog.py   # cria collector/data/catalog_opcoes.csv
python3 collector/seed_history.py     # cria site/data/timeline_seed.json
```

Ambos são versionados no repo; depois disso o coletor é independente no dia a dia.

## Rodar localmente

Pré-requisito: Python 3.9+ (nenhuma biblioteca externa).

```bash
./run_local.sh
# ou manualmente:
python3 collector/collect.py          # gera site/data/data.json (puxa do oficial)
cd site && python3 -m http.server 8000
# abra http://localhost:8000
```

> Não abra o `index.html` com duplo clique (`file://`): o navegador bloqueia a
> leitura do `data.json`. Use sempre um servidor local (o comando acima).

Validar sem gravar nada: `python3 collector/collect.py --check`

### Scripts de diagnóstico (opcionais)

`probe_looker.py`, `probe_filters.py` e `test_looker_table.py` ajudam a inspecionar
o painel oficial e validar a coleta — úteis se o Google mudar algo no `batchedDataV2`.

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
   (Necessário para o bot commitar o `data.json` e o `timeline_state.json`.)
4. **Dispare o primeiro deploy**: aba *Actions* → workflow *Coleta e Deploy* →
   *Run workflow*. Ele coleta os dados, commita os arquivos e publica.
5. Pronto. O site fica em `https://SEU_USUARIO.github.io/SEU_REPO/`.
   A partir daí, atualiza sozinho a cada hora (`cron` no workflow).

Para mudar a frequência, edite o `cron` em `.github/workflows/coleta.yml`
(ex.: `*/30 * * * *` = a cada 30 min).

### Domínio próprio (opcional)
Crie um arquivo `site/CNAME` com seu domínio (ex.: `convocacoes.seudominio.com.br`)
e aponte um registro CNAME no seu DNS para `SEU_USUARIO.github.io`.

## Fonte de dados e adaptadores

O adaptador ativo é o `looker_studio`: lê o **painel oficial da EMBRAPA** via a
consulta pública `batchedDataV2` (acesso anônimo, ~1 requisição/hora — uso leve e
respeitoso de dado público). Parâmetros em `config.py` (`LOOKER_*`).

Se o Google mudar o endpoint/consulta, rode os scripts de diagnóstico
(`probe_looker.py` / `test_looker_table.py`) para recapturar e ajustar.

Adaptadores alternativos continuam disponíveis (basta trocar `EXTRACTOR` em
`config.py`): `upstream_repo` (fonte da comunidade) e o modelo
`google_sheet.py.exemplo` (planilha própria). O `transform.py` e o site **não
mudam** ao trocar de fonte.

## Alternativas de hospedagem

| Opção | Custo | Automação | Observação |
|---|---|---|---|
| **GitHub Pages + Actions** | grátis | cron nativo | recomendado; tudo num repo |
| Cloudflare Pages + Cron Triggers | grátis | via Worker | ótimo desempenho/CDN |
| Netlify + Scheduled Functions | grátis (limites) | cron | simples, build automático |
| VPS + cron + Nginx | pago | cron do SO | mais controle, mais manutenção |

## Aviso

Painel **independente** de acompanhamento, baseado no painel público oficial da
EMBRAPA. Não é um canal oficial da EMBRAPA. As projeções são estimativas
estatísticas e não representam compromisso do órgão. A curva histórica da linha do
tempo foi semeada uma única vez a partir de dados públicos da comunidade; daqui em
diante o histórico é acumulado pelo próprio coletor.
