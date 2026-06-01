"""Registro de adaptadores de extracao."""
from . import upstream_repo

REGISTRY = {
    upstream_repo.UpstreamRepoExtractor.name: upstream_repo.UpstreamRepoExtractor,
}


def get_extractor(name):
    if name not in REGISTRY:
        raise ValueError(f"Extractor '{name}' nao registrado. Disponiveis: {list(REGISTRY)}")
    return REGISTRY[name]()
