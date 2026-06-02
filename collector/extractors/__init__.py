"""Registro de adaptadores de extracao."""
from . import upstream_repo
from . import looker_studio

REGISTRY = {
    upstream_repo.UpstreamRepoExtractor.name: upstream_repo.UpstreamRepoExtractor,
    looker_studio.LookerStudioExtractor.name: looker_studio.LookerStudioExtractor,
}


def get_extractor(name):
    if name not in REGISTRY:
        raise ValueError(f"Extractor '{name}' nao registrado. Disponiveis: {list(REGISTRY)}")
    return REGISTRY[name]()
