#!/usr/bin/env python3
"""Orquestrador do coletor.

Fluxo: extrai dados brutos da fonte ativa -> recalcula metricas ->
grava site/data/data.json. Sai com codigo 0 sempre que gera um arquivo
valido (o commit/deploy fica a cargo do GitHub Actions).

Uso:
    python collector/collect.py            # gera site/data/data.json
    python collector/collect.py --check    # so valida, nao grava
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import EXTRACTOR, VAGAS_EDITAL, FONTE_NOME, FONTE_URL  # noqa: E402
from extractors import get_extractor  # noqa: E402
import transform  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "site", "data", "data.json")

# Campos que mudam a cada execucao mesmo sem novidade real (relogio interno).
# Sao ignorados na comparacao para NAO regravar/commitar a toa.
_VOLATEIS = ("generated_at", "generated_ts", "business_days_elapsed")


def _assinatura(data):
    """Conteudo significativo (sem os campos volateis) para comparar coletas."""
    d = copy.deepcopy(data)
    g = d.get("general", {})
    for k in _VOLATEIS:
        g.pop(k, None)
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def main():
    check = "--check" in sys.argv
    print(f"[coletor] fonte ativa: {EXTRACTOR}")
    raw = get_extractor(EXTRACTOR).fetch()
    print(f"[coletor] brutos -> {len(raw.pessoas)} convocados, "
          f"{len(raw.opcoes)} opcoes, {len(raw.convocacoes)} eventos de convocacao")

    if not raw.pessoas or not raw.opcoes:
        print("[coletor] ERRO: dados brutos incompletos, abortando sem sobrescrever.")
        sys.exit(1)

    data = transform.build(raw)
    data["meta"] = {"fonte_nome": FONTE_NOME, "fonte_url": FONTE_URL,
                    "extractor": EXTRACTOR, "vagas_edital": VAGAS_EDITAL}

    g = data["general"]
    print(f"[coletor] metricas -> {g['total_contratados']} contratados / "
          f"{g['vagas_edital']} vagas | desistencia {g['pct_desistencias']}% | "
          f"{len(data['cumulative']['weekly']['convocado'])} semanas")

    if check:
        print("[coletor] --check OK (nada gravado)")
        return

    # So regrava se houve MUDANCA REAL (assim o Actions nao commita a toa).
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                antigo = json.load(f)
            if _assinatura(antigo) == _assinatura(data):
                print("[coletor] sem mudanca real -> data.json mantido (sem commit)")
                return
        except Exception:  # noqa: BLE001
            pass  # data.json ausente/ilegivel -> grava normalmente

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    kb = os.path.getsize(OUT) / 1024
    print(f"[coletor] MUDANCA detectada -> gravado data.json ({kb:.1f} KB)")


if __name__ == "__main__":
    main()
