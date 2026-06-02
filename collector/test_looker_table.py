#!/usr/bin/env python3
"""Teste end-to-end do adaptador oficial (looker_studio):
  1. coleta as pessoas do painel oficial (anonimo);
  2. recalcula o resumo por opcao a partir dos status + catalogo;
  3. roda o transform e confere as metricas-chave.

Pre-requisito: catalogo gerado (python collector/build_catalog.py).

Uso (na pasta do projeto):
    python collector/test_looker_table.py

Cole a saida no chat.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from extractors.looker_studio import LookerStudioExtractor, _load_catalog  # noqa: E402


def main():
    cat = _load_catalog()
    print(f">> Catalogo: {len(cat)} opcoes carregadas "
          f"({'OK' if cat else 'VAZIO - rode build_catalog.py!'})\n")

    print(">> Coletando do painel oficial...")
    d = LookerStudioExtractor().fetch()
    print(f"   pessoas: {len(d.pessoas)}")
    print(f"   opcoes (resumo recalculado): {len(d.opcoes)}")

    status = {}
    for p in d.pessoas:
        status[p["status"]] = status.get(p["status"], 0) + 1
    print(f"   por status: {status}")

    # quantas pessoas ficaram sem cargo (catalogo nao cobriu a opcao)
    sem_cargo = sum(1 for p in d.pessoas if not p["cargo"])
    print(f"   pessoas sem cargo (opcao fora do catalogo): {sem_cargo}")

    tot_contr = sum(o["contratados"] for o in d.opcoes)
    tot_vagas = sum(o["vagas"] for o in d.opcoes)
    tot_conv = sum(o["convocados"] for o in d.opcoes)
    tot_desist = sum(o["desistencias"] for o in d.opcoes)
    print(f"\n   SOMAS do resumo por opcao:")
    print(f"     contratados={tot_contr}  vagas={tot_vagas}  "
          f"convocados={tot_conv}  desistencias={tot_desist}")

    # por cargo
    porcargo = {}
    for o in d.opcoes:
        c = porcargo.setdefault(o["cargo"] or "(sem)", {"vagas": 0, "contr": 0})
        c["vagas"] += o["vagas"]
        c["contr"] += o["contratados"]
    print("\n   por cargo (vagas / contratados):")
    for c, v in sorted(porcargo.items()):
        print(f"     {c:<14} vagas={v['vagas']:<5} contratados={v['contr']}")

    print("\n>> Rodando transform.build()...")
    try:
        import transform
        data = transform.build(d)
        g = data["general"]
        print(f"   OK -> contratados={g.get('total_contratados')} "
              f"vagas_edital={g.get('vagas_edital')} "
              f"desist%={g.get('pct_desistencias')}")
    except Exception as e:  # noqa: BLE001
        print(f"   transform falhou: {type(e).__name__}: {e}")

    print("\nCopie TUDO e cole no chat.")


if __name__ == "__main__":
    main()
