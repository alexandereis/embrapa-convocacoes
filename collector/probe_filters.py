#!/usr/bin/env python3
"""Replica os FILTROS oficiais (dropdowns) do painel pra extrair as listas de
opcoes e cargos — sao queries registradas, entao funcionam sem login.

Replica verbatim:
  - Request 2 (cd-0p1hn94twd -> _H_  e  cd-u7ixwd9twd -> _I_)
  - Request 3 (cd-c2uvz2zoxd -> blend Cargo/Area/Subarea)

Uso (na pasta do projeto):
    python collector/probe_filters.py

Cole a saida no chat.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from config import LOOKER_ENDPOINT  # noqa: E402
from extractors.looker_studio import (  # noqa: E402
    _post, strip_xssi, _find_table, _expand_column,
)

# ---- Request 2 (verbatim): dois dropdowns, campos _H_ e _I_ ----
REQ_FILTERS = json.loads(r'''
{"dataRequest":[{"requestContext":{"reportContext":{"reportId":"081070ee-89c7-4e57-85bc-04d4601aa513","pageId":"80063060","mode":1,"componentId":"cd-0p1hn94twd","displayType":"dimension-filter"},"requestMode":7},"datasetSpec":{"dataset":[{"datasourceId":"71a5a632-8fb5-4044-ad33-6496c93fb112","revisionNumber":0,"parameterOverrides":[]}],"queryFields":[{"name":"qt_6x0hn94twd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_H_"}}],"sortData":[{"sortColumn":{"name":"qt_6x0hn94twd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_H_"}},"sortDir":0}],"includeRowsCount":true,"relatedDimensionMask":{"addDisplay":false,"addUniqueId":false,"addLatLong":false},"paginateInfo":{"startRow":1,"rowsCount":5001},"dsFilterOverrides":[],"filters":[{"filterDefinition":{"filterExpression":{"include":false,"conceptType":0,"concept":{"ns":"t0","name":"qt_gvilia5twd"},"filterConditionType":"NU","stringValues":[""],"numberValues":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"_H_"}}}},"dataSubsetNs":{"datasetNs":"d0","tableNs":"t0","contextNs":"c0"},"version":3}],"features":[],"dateRanges":[],"contextNsCount":1,"dateRangeDimensions":[{"name":"qt_lezhn94twd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_N_"}}],"calculatedField":[],"needGeocoding":false,"geoFieldMask":[],"multipleGeocodeFields":[],"timezone":"America/Sao_Paulo"},"role":"main","retryHints":{"useClientControlledRetry":true,"isLastRetry":false,"retryCount":0,"originalRequestId":"cd-0p1hn94twd_0_0"}},{"requestContext":{"reportContext":{"reportId":"081070ee-89c7-4e57-85bc-04d4601aa513","pageId":"80063060","mode":1,"componentId":"cd-u7ixwd9twd","displayType":"dimension-filter"},"requestMode":7},"datasetSpec":{"dataset":[{"datasourceId":"71a5a632-8fb5-4044-ad33-6496c93fb112","revisionNumber":0,"parameterOverrides":[]}],"queryFields":[{"name":"qt_ozjxwd9twd","datasetNs":"d0","tableNs":"t0","resultTransformation":{"analyticalFunction":0,"isRelativeToBase":false,"bypassCanvasFilters":false},"dataTransformation":{"sourceFieldName":"_I_"}}],"sortData":[{"sortColumn":{"name":"qt_ozjxwd9twd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_I_"}},"sortDir":0}],"includeRowsCount":true,"relatedDimensionMask":{"addDisplay":false,"addUniqueId":false,"addLatLong":false},"paginateInfo":{"startRow":1,"rowsCount":5001},"dsFilterOverrides":[],"filters":[{"filterDefinition":{"filterExpression":{"include":false,"conceptType":0,"concept":{"ns":"t0","name":"qt_gvilia5twd"},"filterConditionType":"NU","stringValues":[""],"numberValues":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"_H_"}}}},"dataSubsetNs":{"datasetNs":"d0","tableNs":"t0","contextNs":"c0"},"version":3}],"features":[],"dateRanges":[],"contextNsCount":1,"dateRangeDimensions":[{"name":"qt_nzjxwd9twd","datasetNs":"d0","tableNs":"t0","dataTransformation":{"sourceFieldName":"_N_"}}],"calculatedField":[],"needGeocoding":false,"geoFieldMask":[],"multipleGeocodeFields":[],"timezone":"America/Sao_Paulo"},"role":"main","retryHints":{"useClientControlledRetry":true,"isLastRetry":false,"retryCount":0,"originalRequestId":"cd-u7ixwd9twd_0_0"}}]}
''')

# ---- Request 3 (verbatim): blend que mapeia inscricao -> Opcao / Cargo-Area-Subarea ----
REQ_BLEND = json.loads(r'''
{"dataRequest":[{"requestContext":{"reportContext":{"reportId":"081070ee-89c7-4e57-85bc-04d4601aa513","pageId":"80063060","mode":1,"componentId":"cd-c2uvz2zoxd","displayType":"dimension-filter"},"requestMode":7},"datasetSpec":{"dataset":[{"datasourceId":"71a5a632-8fb5-4044-ad33-6496c93fb112","revisionNumber":0,"parameterOverrides":[]},{"datasourceId":"4c59fc90-cb69-470f-aafc-042ffe9f08f9","revisionNumber":0,"parameterOverrides":[]}],"queryFields":[{"name":"qt_g38s22zoxd","datasetNs":"d1","tableNs":"t0","dataTransformation":{"sourceFieldName":"_102621662__dv0"}}],"sortData":[{"sortColumn":{"name":"qt_g38s22zoxd","datasetNs":"d1","tableNs":"t0","dataTransformation":{"sourceFieldName":"_102621662__dv0"}},"sortDir":0}],"includeRowsCount":true,"relatedDimensionMask":{"addDisplay":false,"addUniqueId":false,"addLatLong":false},"paginateInfo":{"startRow":1,"rowsCount":5001},"blendConfig":{"blockDatasource":{"blocks":[{"id":"block_lrezjh9twd","type":6,"inputBlockIds":[],"outputBlockIds":[],"fields":[],"isExperimental":true,"treeQueryBlockConfig":{"join":{"right":{"query":{"concepts":[{"id":{"id":"t0.qt_3ik5m0zoxd","name":"qt_3ik5m0zoxd","namespace":"t0"},"semantic":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"_76523890_"}}},{"id":{"id":"t0.qt_updcc0zoxd","name":"qt_updcc0zoxd","namespace":"t0"},"semantic":[32],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"_102621662_"}}}],"datasourceId":"4c59fc90-cb69-470f-aafc-042ffe9f08f9"}},"left":{"query":{"datasourceId":"71a5a632-8fb5-4044-ad33-6496c93fb112","concepts":[{"id":{"id":"t0.qt_o1lbqh9twd","name":"qt_o1lbqh9twd","namespace":"t0"},"semantic":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"_H_"}}}]}},"condition":{"and":{"conditions":[{"boolean":{"joinKeyPair":{"leftName":"qt_o1lbqh9twd","rightName":"qt_3ik5m0zoxd"}}}]}},"type":3}}}],"datasourceBlock":{"id":"block_krezjh9twd","type":1,"inputBlockIds":[],"outputBlockIds":[],"fields":[{"columnType":0,"field":{"ns":"t0","name":"_H__dv0","simpleName":"_H__dv0"},"outputName":"H","enabled":true,"conceptType":0,"params":[],"dataType":100,"property":[],"isRepeated":false,"isDefault":false,"ancestors":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"qt_o1lbqh9twd"}},"lookerFilterOnlyFieldAllowedValues":[]},{"columnType":0,"field":{"ns":"t0","name":"_76523890__dv0","simpleName":"_76523890__dv0"},"outputName":"Opção","enabled":true,"conceptType":0,"params":[],"dataType":2,"property":[],"isRepeated":false,"isDefault":false,"ancestors":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"qt_3ik5m0zoxd"}},"lookerFilterOnlyFieldAllowedValues":[]},{"columnType":0,"field":{"ns":"t0","name":"_102621662__dv0","simpleName":"_102621662__dv0"},"outputName":"Cargo/Área/Subárea","enabled":true,"conceptType":0,"params":[],"dataType":100,"property":[],"isRepeated":false,"isDefault":false,"ancestors":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"qt_updcc0zoxd"}},"lookerFilterOnlyFieldAllowedValues":[]}]},"delegatedAccessEnabled":true,"isUnlocked":true,"isCacheable":false,"allowNativeFunctions":false}},"dsFilterOverrides":[],"filters":[{"filterDefinition":{"filterExpression":{"include":false,"conceptType":0,"concept":{"ns":"t0","name":"qt_ai1i2j9twd"},"filterConditionType":"NU","stringValues":[""],"numberValues":[],"queryTimeTransformation":{"dataTransformation":{"sourceFieldName":"_H__dv0"}}}},"dataSubsetNs":{"tableNs":"t0","contextNs":"c0"},"version":3}],"features":[],"dateRanges":[],"contextNsCount":1,"calculatedField":[],"needGeocoding":false,"geoFieldMask":[],"multipleGeocodeFields":[],"timezone":"America/Sao_Paulo"},"role":"main","retryHints":{"useClientControlledRetry":true,"isLastRetry":false,"retryCount":0,"originalRequestId":"cd-c2uvz2zoxd_0_0"}}]}
''')


def dump(label, payload):
    print("=" * 64)
    print(label)
    print("=" * 64)
    try:
        data = strip_xssi(_post(LOOKER_ENDPOINT, payload))
    except Exception as e:  # noqa: BLE001
        print(f"  EXC {type(e).__name__}: {e}")
        return
    for i, dr in enumerate(data.get("dataResponse", [])):
        err = dr.get("errorStatus")
        if err:
            print(f"  resposta[{i}]: errorStatus="
                  f"{err.get('reasonStr')}/{err.get('errorCategoryStr')}")
            continue
        table = _find_table(dr)
        if not table:
            print(f"  resposta[{i}]: sem tableDataset (chaves: {list(dr.keys())})")
            continue
        size = table.get("size", 0)
        total = table.get("totalCount", "?")
        cols = table.get("column", [])
        print(f"  resposta[{i}]: total={total} size={size} colunas={len(cols)}")
        for j, c in enumerate(cols):
            vals = _expand_column(c, size)
            print(f"    coluna {j}: {len(vals)} valores | amostra: "
                  f"{[v for v in vals[:12]]}")


def main():
    print(f"Endpoint: {LOOKER_ENDPOINT}\n")
    dump("FILTROS (campo _H_ = inscricao  e  campo _I_ = ???)", REQ_FILTERS)
    print()
    dump("BLEND (Cargo/Area/Subarea, joined por inscricao)", REQ_BLEND)
    print("\nCopie TUDO e cole no chat.")


if __name__ == "__main__":
    main()
