"""Adaptador: ingere os dados BRUTOS da fonte publica consolidada.

Baixa apenas os arquivos-fonte (lista de convocados, resumo por opcao e os
detalhes datados de convocacoes/contratacoes). NAO usa as metricas ja
agregadas da fonte -- essas sao recalculadas em transform.py.

Para migrar para outra fonte (ex.: planilha Google propria), basta criar um
novo extractor que devolva o mesmo objeto RawData.
"""
import csv
import io
import json
import os
import time
import urllib.request

from .base import BaseExtractor, RawData
from config import UPSTREAM_REPO, UPSTREAM_BRANCH

RAW = f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/{UPSTREAM_BRANCH}/data"
API = f"https://api.github.com/repos/{UPSTREAM_REPO}/contents/data?ref={UPSTREAM_BRANCH}"


def _get(url, auth=False, retries=3):
    headers = {"User-Agent": "embrapa-collector"}
    # No GitHub Actions, GITHUB_TOKEN eleva o rate limit da API para 1000/h.
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if auth and token:
        headers["Authorization"] = f"Bearer {token}"
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8-sig")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def _csv(text):
    return list(csv.reader(io.StringIO(text)))


def _num(v):
    try:
        return float(str(v).replace("%", "").replace(",", ".").strip() or 0)
    except ValueError:
        return 0


class UpstreamRepoExtractor(BaseExtractor):
    name = "upstream_repo"

    def fetch(self) -> RawData:
        d = RawData()

        # ---- lista de convocados (current_status.csv) ----
        rows = _csv(_get(f"{RAW}/current_status.csv"))
        d.last_update = rows[0][1] if rows and len(rows[0]) > 1 else ""
        for r in rows[2:]:
            if len(r) < 6:
                continue
            d.pessoas.append({
                "colocacao": r[0], "nome": r[1], "opcao": r[2],
                "status": r[3], "unidade": (r[4] or "").strip(), "lotacao": r[5],
            })

        # ---- resumo por opcao (opcao_status_summary_<ts>.csv) ----
        idx = json.loads(_get(API, auth=True))
        fname = next((x["name"] for x in idx
                      if x["name"].startswith("opcao_status_summary_")
                      and x["name"].endswith(".csv")), None)
        if fname:
            rows = _csv(_get(f"{RAW}/{fname}"))
            for r in rows[2:]:
                if not r or not r[0]:
                    continue
                d.opcoes.append({
                    "opcao": r[0], "cargo": r[1], "area": r[2], "subarea": r[3],
                    "vagas": int(_num(r[4])), "aguardando": int(_num(r[5])),
                    "em_contratacao": int(_num(r[6])), "contratados": int(_num(r[7])),
                    "pct": int(_num(r[8])), "convocados": int(_num(r[9])),
                    "desistencias": int(_num(r[10])),
                })

        # ---- eventos datados para recomputar series ----
        rows = _csv(_get(f"{RAW}/stats/convocados_semanal_detalhes.csv"))
        h = rows[0]
        for r in rows[1:]:
            rec = dict(zip(h, r))
            if rec.get("DATE"):
                d.convocacoes.append({"date": rec["DATE"][:10], "cargo": rec.get("CARGO", "")})

        rows = _csv(_get(f"{RAW}/stats/contratados_mensal_detalhes.csv"))
        h = rows[0]
        for r in rows[1:]:
            rec = dict(zip(h, r))
            if rec.get("DATE"):
                d.contratacoes.append({"date": rec["DATE"][:10], "cargo": rec.get("CARGO", "")})

        # ---- complementos prontos (campos que exigem historico fino) ----
        try:
            d.extras = json.loads(_get(f"{RAW}/stats/general_stats.json"))
        except Exception:
            d.extras = {}

        return d
