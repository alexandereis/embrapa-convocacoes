"""Interface comum a todos os adaptadores de fonte de dados.

Um extractor so precisa devolver os DADOS BRUTOS num dicionario padronizado.
Todo o calculo de metricas acontece em transform.py, entao qualquer fonte
nova (planilha Google, PDF da Embrapa, API propria) so precisa preencher
estes campos.
"""
from dataclasses import dataclass, field


@dataclass
class RawData:
    last_update: str = ""
    pessoas: list = field(default_factory=list)
    opcoes: list = field(default_factory=list)
    convocacoes: list = field(default_factory=list)
    contratacoes: list = field(default_factory=list)
    extras: dict = field(default_factory=dict)


class BaseExtractor:
    name = "base"

    def fetch(self) -> "RawData":  # pragma: no cover
        raise NotImplementedError
