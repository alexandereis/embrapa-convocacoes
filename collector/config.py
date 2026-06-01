"""Configuracao central do coletor.

Para trocar a FONTE de dados, altere apenas EXTRACTOR e os parametros abaixo.
Toda a logica de calculo das metricas e independente da fonte.
"""

# Adaptador de extracao ativo (ver collector/extractors/).
# Opcoes incluidas: "upstream_repo". Para usar uma planilha Google propria,
# crie collector/extractors/google_sheet.py e aponte aqui.
EXTRACTOR = "upstream_repo"

# Parametros do adaptador upstream_repo (fonte publica consolidada).
UPSTREAM_REPO = "arjonilla87/embrapa-site"
UPSTREAM_BRANCH = "main"

# Total de vagas previstas no edital (fallback, caso a fonte nao traga).
VAGAS_EDITAL = 1027

# Credito da fonte exibido no rodape do site.
FONTE_NOME = "controle publico de convocacoes (planilha consolidada da comunidade)"
FONTE_URL = "https://github.com/arjonilla87/embrapa-site"
