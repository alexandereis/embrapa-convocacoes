#!/usr/bin/env python3
"""Sonda de descoberta do painel oficial (Looker Studio / batchedDataV2).

NAO faz parte do pipeline. Serve so para, rodando na SUA maquina:
  1. descobrir qual endpoint responde SEM login (o coletor roda sem cookies);
  2. revelar o conteudo dos campos da fonte principal (em especial _I_ e a
     data _N_), pra gente mapear certo antes de virar a chave em producao.

Uso (a partir da pasta do projeto):
    python3 collector/probe_looker.py

Cole aqui a saida inteira que ela imprimir.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from config import (  # noqa: E402
    LOOKER_REPORT_ID, LOOKER_PAGE_ID, LOOKER_DATASOURCE_ID,
    LOOKER_COMPONENT_ID, LOOKER_TIMEZONE,
)

# Endpoints candidatos, do mais provavel (anonimo/publico) ao menos.
ENDPOINTS = [
    "https://lookerstudio.google.com/embed/batchedDataV2",
    "https://datastudio.google.com/embed/batchedDataV2",
    "https://lookerstudio.google.com/batchedDataV2",
    "https://datastudio.google.com/u/0/batchedDataV2?appVersion=20260526_0400",
]

# Campos a investigar. Os 6 primeiros ja sao conhecidos; _I_ e _N_ sao as
# incognitas (dimensao extra e data). So uso letras que JA apareceram nos
# payloads reais, pra nao arriscar erro de campo inexistente.
PROBE_FIELDS = [
    ("_D_", "colocacao (conhecido)"),
    ("_E_", "nome (conhecido)"),
    ("_H_", "inscricao (conhecido)"),
    ("_Q_", "status (conhecido)"),
    ("_J_", "unidade (conhecido)"),
    ("_K_", "lotacao/cidade (conhecido)"),
    ("_I_", "??? incognita"),
    ("_N_", "??? data (incognita)"),
]


def _qf(name, source):
    return {"name": name, "datasetNs": "d0", "tableNs": "t0",
            "resultTransformation": {"analyticalFunction": 0,
                                     "isRelativeToBase": False,
                                     "bypassCanvasFilters": False},
            "dataTransformation": {"sourceFieldName": source}}


def build_payload(rows=8):
    qfields = [_qf(f"qt_probe{i}", src) for i, (src, _d) in enumerate(PROBE_FIELDS)]
    return {"dataRequest": [{
        "requestContext": {"reportContext": {
            "reportId": LOOKER_REPORT_ID, "pageId": LOOKER_PAGE_ID, "mode": 1,
            "componentId": LOOKER_COMPONENT_ID, "displayType": "simple-table"},
            "requestMode": 0},
        "datasetSpec": {
            "dataset": [{"datasourceId": LOOKER_DATASOURCE_ID,
                         "revisionNumber": 0, "parameterOverrides": []}],
            "queryFields": qfields,
            "sortData": [],
            "includeRowsCount": True,
            "relatedDimensionMask": {"addDisplay": False, "addUniqueId": False,
                                     "addLatLong": False},
            "paginateInfo": {"startRow": 1, "rowsCount": rows},
            "dsFilterOverrides": [],
            "filters": [],
            "features": [], "dateRanges": [], "contextNsCount": 1,
            "calculatedField": [], "needGeocoding": False, "geoFieldMask": [],
            "multipleGeocodeFields": [], "timezone": LOOKER_TIMEZONE},
        "role": "main",
        "retryHints": {"useClientControlledRetry": True, "isLastRetry": False,
                       "retryCount": 0,
                       "originalRequestId": f"{LOOKER_COMPONENT_ID}_0_0"}}]}


def post(endpoint, payload):
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/plain, */*",
               "User-Agent": "Mozilla/5.0 (embrapa-collector-probe)",
               "X-Requested-With": "XMLHttpRequest",
               "Origin": "https://lookerstudio.google.com",
               "Referer": "https://lookerstudio.google.com/"}
    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.status, r.read().decode("utf-8")


def strip_xssi(text):
    i = text.find("{")
    if i == -1:
        raise ValueError("sem corpo JSON")
    return json.loads(text[i:])


def expand(col, size):
    nidx = set(col.get("nullIndex", []) or [])
    vals = None
    for k, v in col.items():
        if k.endswith("Column") and isinstance(v, dict) and "values" in v:
            vals = v["values"]
            break
    it = iter(vals or [])
    return [None if i in nidx else next(it, None) for i in range(size)]


def main():
    payload = build_payload()
    print("=" * 70)
    print("SONDA LOOKER STUDIO — testando endpoints (sem login)")
    print("=" * 70)
    ok_text = None
    for ep in ENDPOINTS:
        try:
            status, text = post(ep, payload)
            head = text[:80].replace("\n", " ")
            if "dataResponse" in text:
                print(f"[OK ]  {ep}\n       HTTP {status} — resposta valida")
                ok_text = text
                print(f"\n>>> ENDPOINT QUE FUNCIONOU: {ep}\n")
                break
            else:
                print(f"[?? ]  {ep}\n       HTTP {status} — sem 'dataResponse'. Inicio: {head}")
        except Exception as e:  # noqa: BLE001
            print(f"[ERR]  {ep}\n       {type(e).__name__}: {e}")
    if not ok_text:
        print("\nNenhum endpoint anonimo respondeu. Cole esta saida que eu "
              "ajusto (pode ser que o relatorio exija cookies / outro caminho).")
        return

    # salva a resposta crua pra inspecao
    raw_path = os.path.join(os.path.dirname(__file__), "probe_raw.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(ok_text)
    print(f"(resposta crua salva em {raw_path})\n")

    data = strip_xssi(ok_text)

    def find_table(obj):
        """Procura recursivamente o primeiro 'tableDataset' na resposta."""
        if isinstance(obj, dict):
            if "tableDataset" in obj:
                return obj["tableDataset"]
            for v in obj.values():
                r = find_table(v)
                if r is not None:
                    return r
        elif isinstance(obj, list):
            for v in obj:
                r = find_table(v)
                if r is not None:
                    return r
        return None

    # mostra a estrutura de alto nivel (ajuda a diagnosticar)
    ds0 = data.get("dataResponse", [{}])[0]
    print("Chaves de dataResponse[0]:", list(ds0.keys()))
    sub = ds0.get("dataSubset")
    if sub:
        print("Chaves de dataSubset[0]:", list(sub[0].keys()))
        ds_inner = sub[0].get("dataset")
        if ds_inner is not None:
            print("Chaves de dataSubset[0]['dataset']:", list(ds_inner.keys()))
    print()

    table = find_table(data)
    if table is None:
        print("NAO achei tableDataset. Inicio da resposta crua:")
        print(ok_text[:1500])
        print("\nCole esta saida + o conteudo de probe_raw.json que eu ajusto.")
        return

    size = table.get("size", 0)
    total = table.get("totalCount", "?")
    cols = table.get("column", [])
    print(f"totalCount = {total} | linhas nesta amostra = {size} | "
          f"colunas = {len(cols)}\n")
    print("AMOSTRA POR CAMPO (pra identificar _I_ e _N_):")
    print("-" * 70)
    for idx, (src, desc) in enumerate(PROBE_FIELDS):
        if idx >= len(cols):
            print(f"{src:<5} {desc:<22} -> (coluna ausente na resposta)")
            continue
        vals = expand(cols[idx], size)
        amostra = ", ".join(repr(v) for v in vals[:6])
        print(f"{src:<5} {desc:<22} -> {amostra}")
    print("-" * 70)
    print("\nPronto. Copie TUDO acima e cole no chat.")


if __name__ == "__main__":
    main()
