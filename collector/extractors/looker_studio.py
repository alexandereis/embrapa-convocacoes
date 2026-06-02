"""Adaptador: extrai os DADOS BRUTOS direto do painel OFICIAL (Looker Studio).

Replica a requisicao `batchedDataV2` que o painel publico do concurso faz ao
ser aberto, paginando TODAS as linhas da tabela de convocados. Nada vem
agregado: o transform.py recalcula as metricas a partir das `pessoas`.

Por que assim: torna o painel independente de fontes de terceiros. Basta o
painel oficial continuar publico para a coleta funcionar.

LIMITACAO ATUAL: este adaptador cobre apenas o componente da TABELA DE
CONVOCADOS (campos _D_,_E_,_H_,_Q_,_J_,_K_). Esse componente NAO traz datas
nem o resumo por opcao/cargo. Para o painel ficar 100% independente ainda
faltam dois componentes do mesmo relatorio (ver COMPONENTS abaixo):
  - resumo por opcao (vagas/contratados/convocados/desistencias por cargo);
  - eventos datados de convocacao/contratacao (para as series temporais).
Enquanto eles nao forem mapeados, use o adaptador `upstream_repo` para esses
campos, ou rode em modo hibrido (ver config.py).
"""
import csv
import json
import os
import time
import urllib.request
from collections import defaultdict

from .base import BaseExtractor, RawData
from config import (
    LOOKER_ENDPOINT,
    LOOKER_REPORT_ID,
    LOOKER_PAGE_ID,
    LOOKER_DATASOURCE_ID,
    LOOKER_COMPONENT_ID,
    LOOKER_TIMEZONE,
    LOOKER_PAGE_SIZE,
    LOOKER_CATALOG,
)


def _load_catalog():
    """Le o catalogo estatico opcao->cargo/area/subarea/vagas (gerado uma vez
    por build_catalog.py). Devolve dict {codigo_opcao: {...}}."""
    path = LOOKER_CATALOG
    if not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), path)
    cat = {}
    if not os.path.exists(path):
        return cat
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = (row.get("OPCAO") or "").strip()
            if not code:
                continue
            try:
                vagas = int(float(row.get("VAGAS") or 0))
            except ValueError:
                vagas = 0
            cat[code] = {
                "cargo": (row.get("CARGO") or "").strip(),
                "area": (row.get("AREA") or "").strip(),
                "subarea": (row.get("SUBAREA") or "").strip(),
                "vagas": vagas,
            }
    return cat

# ---------------------------------------------------------------------------
# Mapa de campos da TABELA DE CONVOCADOS.
# A chave externa e o sourceFieldName (estavel no relatorio); a 'queryName' e
# o id efemero da coluna (qt_...). A ORDEM aqui define a ordem das queryFields
# enviadas E a ordem em que lemos as colunas da resposta.
# ---------------------------------------------------------------------------
TABLE_FIELDS = [
    # (sourceFieldName, chave_no_modelo, queryName)
    # ATENCAO: _H_ e o CODIGO DA OPCAO (ex.: 40000084), nao a inscricao do
    # candidato. Cada opcao = um Cargo/Area/Subarea com N vagas; varios
    # convocados compartilham o mesmo codigo de opcao.
    ("_D_", "colocacao", "qt_1pxv074twd"),
    ("_E_", "nome",      "qt_otdav44twd"),
    ("_H_", "opcao",     "qt_nc73k64twd"),
    ("_Q_", "status",    "qt_5go3364twd"),
    ("_J_", "unidade",   "qt_duqvbfyxyd"),
    ("_K_", "lotacao",   "qt_ge9totyxyd"),
]

# Status oficiais observados -> buckets do resumo por opcao.
STATUS_CONTRATADO = {"Contratado"}
STATUS_EM_CONTRATACAO = {"Aceitou"}
STATUS_AGUARDANDO = {"Convocado"}
STATUS_DESISTENCIA = {"Desistente", "Desclassificado", "Não se manifestou"}


def _query_field(name, source):
    return {
        "name": name,
        "datasetNs": "d0",
        "tableNs": "t0",
        "resultTransformation": {
            "analyticalFunction": 0,
            "isRelativeToBase": False,
            "bypassCanvasFilters": False,
        },
        "dataTransformation": {"sourceFieldName": source},
    }


def _build_payload(start_row, rows_count):
    """Monta o corpo do batchedDataV2 para uma pagina da tabela de convocados.

    Mantem os MESMOS filtros e ordenacao do painel (exclui _A_/_G_ nulos e _D_
    vazio), que sao o que reduz o dataset as ~1045 linhas validas.
    """
    query_fields = [_query_field(q, s) for (s, _k, q) in TABLE_FIELDS]
    return {
        "dataRequest": [{
            "requestContext": {
                "reportContext": {
                    "reportId": LOOKER_REPORT_ID,
                    "pageId": LOOKER_PAGE_ID,
                    "mode": 1,
                    "componentId": LOOKER_COMPONENT_ID,
                    "displayType": "simple-table",
                },
                "requestMode": 0,
            },
            "datasetSpec": {
                "dataset": [{
                    "datasourceId": LOOKER_DATASOURCE_ID,
                    "revisionNumber": 0,
                    "parameterOverrides": [],
                }],
                "queryFields": query_fields,
                "sortData": [
                    {"sortColumn": {"name": "qt_1pxv074twd", "datasetNs": "d0",
                                    "tableNs": "t0",
                                    "dataTransformation": {"sourceFieldName": "_D_"}},
                     "sortDir": 0},
                    {"sortColumn": {"name": "qt_rfmzqsixwd", "datasetNs": "d0",
                                    "tableNs": "t0",
                                    "dataTransformation": {"sourceFieldName": "_C_",
                                                           "aggregation": 6}},
                     "sortDir": 0},
                ],
                "includeRowsCount": True,
                "relatedDimensionMask": {"addDisplay": False, "addUniqueId": False,
                                         "addLatLong": False},
                "paginateInfo": {"startRow": start_row, "rowsCount": rows_count},
                "dsFilterOverrides": [],
                "filters": [
                    {"filterDefinition": {"filterExpression": {
                        "include": False, "conceptType": 0,
                        "concept": {"ns": "t0", "name": "qt_1s3l3awqwd"},
                        "filterConditionType": "NU", "stringValues": [],
                        "numberValues": [],
                        "queryTimeTransformation": {"dataTransformation": {
                            "sourceFieldName": "_A_", "aggregation": 0}}}},
                     "dataSubsetNs": {"datasetNs": "d0", "tableNs": "t0",
                                      "contextNs": "c0"}, "version": 3},
                    {"filterDefinition": {"filterExpression": {
                        "include": False, "conceptType": 0,
                        "concept": {"ns": "t0", "name": "qt_apxykcxqwd"},
                        "filterConditionType": "NU", "stringValues": [],
                        "numberValues": [],
                        "queryTimeTransformation": {"dataTransformation": {
                            "sourceFieldName": "_G_", "aggregation": 0}}}},
                     "dataSubsetNs": {"datasetNs": "d0", "tableNs": "t0",
                                      "contextNs": "c0"}, "version": 3},
                    {"filterDefinition": {"filterExpression": {
                        "include": False, "conceptType": 0,
                        "concept": {"ns": "t0", "name": "qt_4y2av84twd"},
                        "filterConditionType": "NU", "stringValues": [""],
                        "numberValues": [],
                        "queryTimeTransformation": {"dataTransformation": {
                            "sourceFieldName": "_D_"}}}},
                     "dataSubsetNs": {"datasetNs": "d0", "tableNs": "t0",
                                      "contextNs": "c0"}, "version": 3},
                ],
                "features": [],
                "dateRanges": [],
                "contextNsCount": 1,
                "calculatedField": [],
                "needGeocoding": False,
                "geoFieldMask": [],
                "multipleGeocodeFields": [],
                "timezone": LOOKER_TIMEZONE,
            },
            "role": "main",
            "retryHints": {"useClientControlledRetry": True, "isLastRetry": False,
                           "retryCount": 0,
                           "originalRequestId": f"{LOOKER_COMPONENT_ID}_0_0"},
        }],
    }


# ---------------------------------------------------------------------------
# Parsing da resposta
# ---------------------------------------------------------------------------
def strip_xssi(text):
    """Remove o prefixo anti-XSSI do Looker Studio (ex.: ")]}'\n") e devolve
    o JSON. Robusto: corta tudo antes do primeiro '{'."""
    i = text.find("{")
    if i == -1:
        raise ValueError("Resposta sem corpo JSON.")
    return json.loads(text[i:])


def _column_values(col):
    """Extrai a lista de valores de uma coluna, seja qual for o tipo
    (stringColumn/longColumn/doubleColumn/...)."""
    for key, val in col.items():
        if key.endswith("Column") and isinstance(val, dict) and "values" in val:
            return val["values"]
    return []


def _expand_column(col, size):
    """Reconstroi a coluna completa (tamanho `size`) reinserindo None nas
    posicoes listadas em nullIndex. O array `values` so contem os NAO-nulos."""
    null_idx = set(col.get("nullIndex", []) or [])
    vals = iter(_column_values(col))
    out = []
    for i in range(size):
        out.append(None if i in null_idx else next(vals, None))
    return out


def _find_table(obj):
    """Acha recursivamente o primeiro 'tableDataset' na resposta."""
    if isinstance(obj, dict):
        if "tableDataset" in obj:
            return obj["tableDataset"]
        for v in obj.values():
            r = _find_table(v)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_table(v)
            if r is not None:
                return r
    return None


def parse_table(resp_json):
    """Recebe o JSON ja decodificado e devolve (rows, total_count).

    `rows` e uma lista de dicts ja mapeados pelas chaves de TABLE_FIELDS.
    """
    dr = resp_json.get("dataResponse", [{}])[0]
    err = dr.get("errorStatus")
    if err:
        raise ValueError(
            "Looker recusou a query (errorStatus): "
            f"{err.get('reasonStr')} / {err.get('errorCategoryStr')}. "
            "Em acesso anonimo so valem as queries EXATAS dos componentes do "
            "painel (mesmos campos, filtros e ordenacao).")
    table = _find_table(resp_json)
    if table is None:
        raise ValueError("Resposta sem tableDataset e sem errorStatus.")
    total = table.get("totalCount", 0)
    size = table.get("size", 0)
    cols = table.get("column", [])
    # Pagina vazia (ex.: startRow alem do fim) -> fim da coleta, sem erro.
    if size == 0 or not cols:
        return [], total
    if len(cols) != len(TABLE_FIELDS):
        raise ValueError(
            f"Esperava {len(TABLE_FIELDS)} colunas, recebi {len(cols)}. "
            "O mapa TABLE_FIELDS pode estar fora de ordem com a query.")
    expanded = [_expand_column(c, size) for c in cols]
    keys = [k for (_s, k, _q) in TABLE_FIELDS]
    rows = []
    for r in range(size):
        rows.append({keys[c]: expanded[c][r] for c in range(len(keys))})
    return rows, total


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _post(endpoint, payload, retries=3):
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (embrapa-collector)",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://lookerstudio.google.com",
        "Referer": "https://lookerstudio.google.com/",
    }
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(endpoint, data=body, headers=headers,
                                         method="POST")
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("utf-8")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


class LookerStudioExtractor(BaseExtractor):
    name = "looker_studio"

    def fetch(self) -> RawData:
        d = RawData()
        # horario de Brasilia (UTC-3), formato dd/mm/aaaa HH:MM
        _br = time.gmtime(time.time() - 3 * 3600)
        d.last_update = time.strftime("%d/%m/%Y %H:%M", _br)
        catalog = _load_catalog()

        start, page = 1, LOOKER_PAGE_SIZE
        total = None
        seen = set()
        guard = 0
        while True:
            guard += 1
            if guard > 200:  # trava de seguranca contra loop infinito
                break
            # clampa a ultima pagina pra NAO pedir alem do fim (startRow+rows
            # ultrapassando o totalCount faz o Looker devolver pagina vazia).
            req_rows = page if total is None else min(page, total - start + 1)
            if total is not None and req_rows <= 0:
                break
            raw_text = _post(LOOKER_ENDPOINT, _build_payload(start, req_rows))
            rows, total = parse_table(strip_xssi(raw_text))
            if not rows:
                break
            for i, p in enumerate(rows):
                cod = (p.get("opcao") or "").strip()
                cat = catalog.get(cod, {})
                # chave inclui a posicao absoluta -> nao descarta homonimos
                key = (start + i, cod, p.get("colocacao"))
                if key in seen:
                    continue
                seen.add(key)
                d.pessoas.append({
                    "colocacao": (p.get("colocacao") or "").strip(),
                    "nome": (p.get("nome") or "").strip(),
                    "opcao": cod,                       # codigo da opcao (_H_)
                    "cargo": cat.get("cargo", ""),      # via catalogo
                    "area": cat.get("area", ""),
                    "subarea": cat.get("subarea", ""),
                    "status": (p.get("status") or "").strip(),
                    "unidade": (p.get("unidade") or "").strip(),
                    "lotacao": (p.get("lotacao") or "").strip(),
                })
            # avanca pelo numero de linhas REALMENTE recebidas
            start += len(rows)
            if total and start > total:
                break
            if len(rows) < req_rows:  # ultima pagina (servidor devolveu menos)
                break

        # ---- resumo por opcao: RECALCULADO dos status oficiais + catalogo ----
        agg = defaultdict(lambda: {"convocados": 0, "contratados": 0,
                                   "em_contratacao": 0, "aguardando": 0,
                                   "desistencias": 0})
        for p in d.pessoas:
            a = agg[p["opcao"]]
            a["convocados"] += 1  # estar na tabela = foi convocado
            s = p["status"]
            if s in STATUS_CONTRATADO:
                a["contratados"] += 1
            elif s in STATUS_EM_CONTRATACAO:
                a["em_contratacao"] += 1
            elif s in STATUS_AGUARDANDO:
                a["aguardando"] += 1
            elif s in STATUS_DESISTENCIA:
                a["desistencias"] += 1
        zero = {"convocados": 0, "contratados": 0, "em_contratacao": 0,
                "aguardando": 0, "desistencias": 0}
        # uniao: TODAS as opcoes do catalogo (mesmo as ainda sem convocacao)
        # + qualquer opcao convocada que por acaso nao esteja no catalogo.
        for cod in sorted(set(catalog) | set(agg)):
            a = agg.get(cod, zero)
            cat = catalog.get(cod, {})
            vagas = cat.get("vagas", 0)
            preenchido = a["contratados"] + a["em_contratacao"]
            pct = round(100 * preenchido / vagas) if vagas else 0
            d.opcoes.append({
                "opcao": cod,
                "cargo": cat.get("cargo", ""),
                "area": cat.get("area", ""),
                "subarea": cat.get("subarea", ""),
                "vagas": vagas,
                "aguardando": a["aguardando"],
                "em_contratacao": a["em_contratacao"],
                "contratados": a["contratados"],
                "pct": pct,
                "convocados": a["convocados"],
                "desistencias": a["desistencias"],
            })

        # ---- linha do tempo: seed historico + acumulo proprio ----
        # A tabela oficial nao traz datas. timeline.py mantem a serie (curva
        # historica semeada uma vez + snapshots por coleta). Defensivo: se algo
        # falhar, a coleta continua, so a timeline fica como estiver.
        try:
            from timeline import update_and_build
            conv, contr, extras = update_and_build(d.pessoas)
            d.convocacoes = conv
            d.contratacoes = contr
            d.extras = extras or {}
        except Exception:  # noqa: BLE001
            pass

        return d
