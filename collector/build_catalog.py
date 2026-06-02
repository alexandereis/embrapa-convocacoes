#!/usr/bin/env python3
"""Gera (uma vez) o catalogo estatico opcao -> cargo/area/subarea/vagas.

O catalogo e dado de EDITAL (lista de opcoes e numero de vagas) — nao muda
durante as convocacoes. Geramos a partir do resumo publico consolidado da
comunidade SO PARA OS CAMPOS ESTATICOS (cargo/area/subarea/vagas); os numeros
dinamicos (contratados, convocados, desistencias) o coletor recalcula do
painel OFICIAL. O arquivo gerado fica versionado no repo, entao a coleta do
dia a dia nao depende de terceiros.

Uso (na pasta do projeto), apenas quando quiser (re)gerar o catalogo:
    python collector/build_catalog.py
"""
import csv
import io
import os
import urllib.request

SRC = ("https://raw.githubusercontent.com/arjonilla87/embrapa-site/"
       "main/data/opcao_status_summary.csv")
OUT = os.path.join(os.path.dirname(__file__), "data", "catalog_opcoes.csv")


def main():
    req = urllib.request.Request(SRC, headers={"User-Agent": "embrapa-collector"})
    text = urllib.request.urlopen(req, timeout=30).read().decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))

    # acha a linha de cabecalho (comeca em "OPÇÃO")
    hi = next((i for i, r in enumerate(rows) if r and r[0].strip() == "OPÇÃO"), None)
    if hi is None:
        raise SystemExit("Cabecalho 'OPÇÃO' nao encontrado na fonte.")
    header = [h.strip() for h in rows[hi]]
    idx = {name: i for i, name in enumerate(header)}
    req_cols = ["OPÇÃO", "CARGO", "ÁREA", "SUBÁREA", "TOTAL VAGAS"]
    for c in req_cols:
        if c not in idx:
            raise SystemExit(f"Coluna '{c}' ausente na fonte. Cabecalho: {header}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    n = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["OPCAO", "CARGO", "AREA", "SUBAREA", "VAGAS"])
        for r in rows[hi + 1:]:
            if not r or not (r[idx["OPÇÃO"]] or "").strip():
                continue
            w.writerow([
                r[idx["OPÇÃO"]].strip(),
                r[idx["CARGO"]].strip(),
                r[idx["ÁREA"]].strip(),
                r[idx["SUBÁREA"]].strip(),
                r[idx["TOTAL VAGAS"]].strip(),
            ])
            n += 1
    print(f"catalogo gravado: {OUT} ({n} opcoes)")


if __name__ == "__main__":
    main()
