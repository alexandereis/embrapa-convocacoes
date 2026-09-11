#!/usr/bin/env python3
"""Sonda de diagnostico da FONTE (painel oficial / Looker).

Serve para responder uma pergunta especifica: qual GERACAO do conjunto a fonte
esta servindo para ESTE ambiente? A fonte mantem varias entradas de cache e ja
foi vista servindo uma geracao antiga para um ambiente enquanto servia a atual
para outro (em 11/09/2026 o runner do GitHub Actions lia 1157 linhas enquanto a
maquina local e o worker liam 1169).

Uso:
    python collector/probe_fonte.py            # leituras repetidas (padrao)
    python collector/probe_fonte.py --rows     # varre valores de rowsCount
"""
import collections
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import LOOKER_ENDPOINT, LOOKER_ROWS_REGISTRADO  # noqa: E402
from extractors.looker_studio import (  # noqa: E402
    _build_payload, _post, parse_table, strip_xssi,
)

REPETICOES = 8
ROWS_COUNTS = (500, 1000, 1169, 2000, 5000)


def _ler(rows_count, start=1):
    rows, total = parse_table(strip_xssi(
        _post(LOOKER_ENDPOINT, _build_payload(start, rows_count))))
    return len(rows), total


def repetidas():
    print(f"== {REPETICOES} leituras da query REGISTRADA "
          f"(rowsCount={LOOKER_ROWS_REGISTRADO}) ==")
    vistos = collections.Counter()
    for i in range(REPETICOES):
        try:
            n, total = _ler(LOOKER_ROWS_REGISTRADO)
            vistos[total] += 1
            print(f"  #{i + 1:>2} totalCount={total} linhas={n}")
        except Exception as e:  # noqa: BLE001
            print(f"  #{i + 1:>2} ERRO: {e}")
        time.sleep(2)
    print(f"  geracoes vistas: {dict(vistos)}")
    if len(vistos) > 1:
        print("  => a fonte OSCILA entre geracoes neste ambiente")
    elif vistos:
        print(f"  => estavel em {next(iter(vistos))} linhas neste ambiente")


def por_rows_count():
    print("== totalCount por rowsCount (startRow=1) ==")
    for rc in ROWS_COUNTS:
        try:
            n, total = _ler(rc)
            marca = "  <== query registrada" if rc == LOOKER_ROWS_REGISTRADO else ""
            print(f"  rowsCount={rc:<6} totalCount={total:<6} linhas={n}{marca}")
        except Exception as e:  # noqa: BLE001
            print(f"  rowsCount={rc:<6} ERRO: {e}")
        time.sleep(2)


def variantes():
    """Tenta furar o cache do ambiente: headers, URL e campos do payload.

    Se alguma variante devolver mais linhas que a leitura normal, existe um
    jeito barato de pegar a geracao atual sem mudar o caminho da coleta.
    """
    import copy
    import json
    import urllib.request

    base_url = LOOKER_ENDPOINT
    base_payload = _build_payload(1, LOOKER_ROWS_REGISTRADO)

    def pedir(url, payload, extra_headers=None):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (embrapa-collector)",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://lookerstudio.google.com",
            "Referer": "https://lookerstudio.google.com/",
        }
        headers.update(extra_headers or {})
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            _rows, total = parse_table(strip_xssi(r.read().decode("utf-8")))
            return total

    testes = [("normal (referencia)", base_url, base_payload, None)]

    testes.append(("header no-cache", base_url, base_payload,
                   {"Cache-Control": "no-cache, no-store, max-age=0",
                    "Pragma": "no-cache"}))

    testes.append(("cache-buster na URL",
                   base_url + "?_=" + str(int(time.time() * 1000)),
                   base_payload, None))

    testes.append(("endpoint lookerstudio.google.com",
                   "https://lookerstudio.google.com/embed/batchedDataV2",
                   base_payload, None))

    p = copy.deepcopy(base_payload)
    p["dataRequest"][0]["requestContext"]["requestMode"] = 1
    testes.append(("requestMode=1", base_url, p, None))

    p = copy.deepcopy(base_payload)
    p["dataRequest"][0]["retryHints"]["retryCount"] = 1
    p["dataRequest"][0]["retryHints"]["isLastRetry"] = True
    testes.append(("retryCount=1", base_url, p, None))

    p = copy.deepcopy(base_payload)
    p["dataRequest"][0]["datasetSpec"]["dataset"][0]["revisionNumber"] = 1
    testes.append(("revisionNumber=1", base_url, p, None))

    print("== variantes para furar o cache deste ambiente ==")
    referencia = None
    for nome, url, payload, hdrs in testes:
        try:
            total = pedir(url, payload, hdrs)
            if referencia is None:
                referencia = total
            marca = ""
            if referencia is not None and total and total > referencia:
                marca = "   <== MAIS LINHAS (geracao mais nova!)"
            print(f"  {nome:<34} totalCount={total}{marca}")
        except Exception as e:  # noqa: BLE001
            print(f"  {nome:<34} ERRO: {str(e)[:70]}")
        time.sleep(2)


if __name__ == "__main__":
    if "--rows" in sys.argv:
        por_rows_count()
    elif "--variantes" in sys.argv:
        variantes()
    else:
        repetidas()
        print()
        por_rows_count()
        print()
        variantes()
