#!/usr/bin/env python3
"""Testes do transform.py -- roda com `python collector/test_transform.py`."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import transform  # noqa: E402


class TestCota(unittest.TestCase):
    """A cota sai da COLOCACAO, que vem como texto livre da fonte."""

    def test_ampla_concorrencia(self):
        self.assertEqual(transform._cota("10ª AC"), "AC")

    def test_ppp(self):
        self.assertEqual(transform._cota("2º PPP"), "PPP")

    def test_pcd(self):
        self.assertEqual(transform._cota("1º PCD"), "PCD")

    def test_pne_conta_como_pcd(self):
        self.assertEqual(transform._cota("3º PNE"), "PCD")

    def test_reconvocacao_mantem_a_cota(self):
        self.assertEqual(transform._cota("REC 2º PCD"), "PCD")

    def test_pp_truncado_e_ppp(self):
        """A fonte tem uma linha com "1º PP" -- PPP com um caractere perdido.
        Sem isso ela ficava sozinha num balde "Outros" no grafico de cotas."""
        self.assertEqual(transform._cota("1º PP"), "PPP")

    def test_ppp_nao_e_confundido_com_pp(self):
        self.assertEqual(transform._cota("45º PPP"), "PPP")

    def test_colocacao_desconhecida_nao_e_chutada(self):
        self.assertEqual(transform._cota("1º XYZ"), "Outros")

    def test_colocacao_vazia(self):
        self.assertEqual(transform._cota(""), "Outros")


class TestOrdemDosCargos(unittest.TestCase):
    """O catalogo do edital escreve "Técnico" com acento; a ordem procurava
    sem acento e o cargo caia para o fim, depois de Assistente."""

    def test_ordem_canonica(self):
        cargos = ["Assistente", "Técnico", "Analista", "Pesquisador"]
        self.assertEqual(sorted(cargos, key=transform._ordem_cargo),
                         ["Pesquisador", "Analista", "Técnico", "Assistente"])

    def test_cargo_desconhecido_vai_para_o_fim(self):
        self.assertGreater(transform._ordem_cargo("Cargo Novo"),
                           transform._ordem_cargo("Assistente"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
