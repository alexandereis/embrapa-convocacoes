"""Configuracao central do coletor.

Para trocar a FONTE de dados, altere apenas EXTRACTOR e os parametros abaixo.
Toda a logica de calculo das metricas e independente da fonte.
"""

# Adaptador de extracao ativo (ver collector/extractors/).
# Opcoes incluidas: "upstream_repo", "looker_studio".
EXTRACTOR = "looker_studio"

# Parametros do adaptador upstream_repo (fonte publica consolidada).
UPSTREAM_REPO = "arjonilla87/embrapa-site"
UPSTREAM_BRANCH = "main"

# -------------------------------------------------------------------------
# Parametros do adaptador looker_studio (painel OFICIAL, batchedDataV2).
# -------------------------------------------------------------------------
# Request URL capturada no DevTools (sessao logada usa /u/0/). Como o coletor
# roda SEM login (GitHub Actions / urllib local nao tem os cookies do Google),
# o endpoint anonimo de relatorios PUBLICOS costuma ser o /embed/. Se o fetch
# anonimo falhar, troque LOOKER_ENDPOINT pela URL logada abaixo (so funciona
# com cookies validos). O appVersion muda com o tempo; o /embed/ dispensa-o.
#   capturada (logada): https://datastudio.google.com/u/0/batchedDataV2?appVersion=20260526_0400
# CONFIRMADO pela sonda (probe_looker.py): este endpoint anonimo responde 200
# para queries REGISTRADAS do relatorio (o lookerstudio.google.com/embed deu 400).
# Importante: em acesso anonimo o Looker so honra as queries EXATAS dos
# componentes do painel (validacao PREFETCH); nao da pra inventar campos.
LOOKER_ENDPOINT = "https://datastudio.google.com/embed/batchedDataV2"
LOOKER_REPORT_ID = "081070ee-89c7-4e57-85bc-04d4601aa513"
LOOKER_PAGE_ID = "80063060"
LOOKER_DATASOURCE_ID = "71a5a632-8fb5-4044-ad33-6496c93fb112"
LOOKER_COMPONENT_ID = "cd-47x8z6vqwd"
LOOKER_TIMEZONE = "America/Sao_Paulo"
LOOKER_PAGE_SIZE = 500  # linhas por requisicao (a ultima pagina e clampada)
# Catalogo estatico opcao->cargo/area/subarea/vagas (gerado por build_catalog.py).
# Caminho relativo a pasta collector/. E dado de edital: nao muda durante as
# convocacoes, fica versionado no repo -> coletor independente.
LOOKER_CATALOG = "data/catalog_opcoes.csv"

# Total de vagas previstas no edital (fallback, caso a fonte nao traga).
VAGAS_EDITAL = 1027

# Credito da fonte exibido no rodape do site.
FONTE_NOME = "Painel oficial de convocacoes da EMBRAPA (Looker Studio)"
FONTE_URL = ("https://datastudio.google.com/u/0/reporting/"
             "081070ee-89c7-4e57-85bc-04d4601aa513/page/qD6ZF")
