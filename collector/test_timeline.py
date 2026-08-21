#!/usr/bin/env python3
"""Testes do timeline.py -- roda com `python collector/test_timeline.py`.

Cobrem os dois defeitos observados em producao:

  1. A fonte oficial (Looker) as vezes devolve uma GERACAO ANTIGA do conjunto
     (cache velho). Em 2026-08-08 07:05 UTC o coletor recebeu um snapshot
     IDENTICO ao de 2026-08-07 20:31 (1119 linhas) DEPOIS de ja ter coletado a
     geracao nova (1123 linhas). Como toda diferenca virava um evento datado,
     a mesma pessoa aparecia varias vezes com status contraditorios.

  2. A mesma pessoa aparece mais de uma vez na MESMA opcao (uma linha pela
     cota, outra pela ampla concorrencia, ou duas lotacoes). Isso inflava a
     contagem de convocados e quebrava o historico dela.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import timeline  # noqa: E402


def pessoa(nome, status, opcao="40001690", colocacao="1o AC", unidade="CPAA",
           lotacao="Manaus", cargo="Pesquisador"):
    return {"nome": nome, "status": status, "opcao": opcao, "colocacao": colocacao,
            "unidade": unidade, "lotacao": lotacao, "cargo": cargo}


class TimelineTestCase(unittest.TestCase):
    """Isola SEED_PATH/STATE_PATH num diretorio temporario."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._seed, self._state = timeline.SEED_PATH, timeline.STATE_PATH
        timeline.SEED_PATH = os.path.join(self.tmp.name, "seed.json")
        timeline.STATE_PATH = os.path.join(self.tmp.name, "state.json")

    def tearDown(self):
        timeline.SEED_PATH, timeline.STATE_PATH = self._seed, self._state
        self.tmp.cleanup()

    def coletar(self, pessoas):
        """Uma coleta. Devolve os `extras` (onde vivem as mudancas)."""
        return timeline.update_and_build(pessoas)[2]

    def estado(self):
        with open(timeline.STATE_PATH, encoding="utf-8") as f:
            return json.load(f)

    def mudancas_de(self, extras, nome):
        return [c for c in extras.get("changes", []) if c["nome"] == nome]


class TestGeracaoAntigaEmLote(TimelineTestCase):
    """Guarda #1: um LOTE de regressoes simultaneas = geracao antiga da fonte."""

    def test_lote_de_regressoes_simultaneas_e_rejeitado(self):
        atual = [pessoa("ANA", "Contratado"), pessoa("BIA", "Contratado"),
                 pessoa("CIA", "Contratado")]
        self.coletar(atual)                      # baseline
        antiga = [pessoa("ANA", "Aceitou"), pessoa("BIA", "Aceitou"),
                  pessoa("CIA", "Aceitou")]      # a fonte "voltou no tempo"
        with self.assertRaises(timeline.FonteDesatualizada):
            self.coletar(antiga)

    def test_lote_rejeitado_nao_altera_o_estado(self):
        atual = [pessoa("ANA", "Contratado"), pessoa("BIA", "Contratado")]
        self.coletar(atual)
        try:
            self.coletar([pessoa("ANA", "Aceitou"), pessoa("BIA", "Aceitou")])
        except timeline.FonteDesatualizada:
            pass
        people = self.estado()["people"]
        self.assertEqual(list(people.values()), ["Contratado", "Contratado"])

    def test_lote_repetido_a_exaustao_acaba_aceito(self):
        """Escape: se a fonte insistir no mesmo lote, e correcao real, nao cache."""
        self.coletar([pessoa("ANA", "Contratado"), pessoa("BIA", "Contratado")])
        antiga = [pessoa("ANA", "Aceitou"), pessoa("BIA", "Aceitou")]
        aceito = False
        for _ in range(timeline._CONFIRMACOES_LOTE + 2):
            try:
                self.coletar(antiga)
            except timeline.FonteDesatualizada:
                continue
            aceito = True
            break
        self.assertTrue(aceito, "lote repetido deveria ser aceito, nao travar o painel")
        self.assertEqual(set(self.estado()["people"].values()), {"Aceitou"})

    def test_avanco_em_lote_e_aceito_na_hora(self):
        """33 pessoas virando Contratado no mesmo dia e noticia real, nao cache."""
        antes = [pessoa(f"P{i}", "Aceitou") for i in range(33)]
        self.coletar(antes)
        extras = self.coletar([pessoa(f"P{i}", "Contratado") for i in range(33)])
        self.assertEqual(len(extras["changes"]), 33)


class TestRegressaoIsolada(TimelineTestCase):
    """Guarda #2: regressao de 1 pessoa espera confirmacao antes de virar fato."""

    def test_regressao_isolada_nao_vira_evento_na_primeira_leitura(self):
        self.coletar([pessoa("ANA", "Contratado"), pessoa("BIA", "Contratado")])
        extras = self.coletar([pessoa("ANA", "Aceitou"), pessoa("BIA", "Contratado")])
        self.assertEqual(self.mudancas_de(extras, "ANA"), [])

    def test_regressao_isolada_nao_altera_o_status_publicado(self):
        self.coletar([pessoa("ANA", "Contratado"), pessoa("BIA", "Contratado")])
        self.coletar([pessoa("ANA", "Aceitou"), pessoa("BIA", "Contratado")])
        chave = timeline.norm_key("40001690", "ANA")
        self.assertEqual(self.estado()["people"][chave], "Contratado")

    def test_ida_e_volta_nao_deixa_rastro(self):
        """O caso ARIANE/CLEILTON: Aceitou->Convocado->Aceitou em minutos."""
        self.coletar([pessoa("ARIANE", "Aceitou"), pessoa("BIA", "Contratado")])
        self.coletar([pessoa("ARIANE", "Convocado"), pessoa("BIA", "Contratado")])
        extras = self.coletar([pessoa("ARIANE", "Aceitou"), pessoa("BIA", "Contratado")])
        self.assertEqual(self.mudancas_de(extras, "ARIANE"), [])

    def test_regressao_confirmada_duas_vezes_e_aceita(self):
        self.coletar([pessoa("ANA", "Contratado"), pessoa("BIA", "Contratado")])
        volta = [pessoa("ANA", "Aceitou"), pessoa("BIA", "Contratado")]
        self.coletar(volta)
        extras = self.coletar(volta)
        eventos = self.mudancas_de(extras, "ANA")
        self.assertEqual([(e["de"], e["para"]) for e in eventos],
                         [("Contratado", "Aceitou")])

    def test_avanco_normal_e_aceito_na_hora(self):
        self.coletar([pessoa("ANA", "Convocado")])
        extras = self.coletar([pessoa("ANA", "Aceitou")])
        self.assertEqual([(e["de"], e["para"]) for e in self.mudancas_de(extras, "ANA")],
                         [("Convocado", "Aceitou")])

    def test_desistencia_e_aceita_na_hora(self):
        """Desistir depois de aceitar e comum e nunca foi status anterior dela."""
        self.coletar([pessoa("ANA", "Convocado")])
        self.coletar([pessoa("ANA", "Aceitou")])
        extras = self.coletar([pessoa("ANA", "Desistente")])
        self.assertEqual([(e["de"], e["para"]) for e in self.mudancas_de(extras, "ANA")][-1:],
                         [("Aceitou", "Desistente")])


class TestDedupePessoas(TimelineTestCase):
    """A mesma pessoa na MESMA opcao e UMA convocacao, nao duas."""

    def test_mesma_pessoa_mesma_opcao_em_duas_colocacoes_conta_uma_vez(self):
        linhas = [pessoa("GABRIELA", "Desistente", opcao="40000188", colocacao="2o PPP"),
                  pessoa("GABRIELA", "Desistente", opcao="40000188", colocacao="45o AC")]
        self.assertEqual(len(timeline.dedupe_pessoas(linhas)), 1)

    def test_mesma_pessoa_em_opcoes_diferentes_conta_duas_vezes(self):
        linhas = [pessoa("ABIAS", "Desistente", opcao="40003735"),
                  pessoa("ABIAS", "Contratado", opcao="40001749")]
        self.assertEqual(len(timeline.dedupe_pessoas(linhas)), 2)

    def test_colapso_prefere_a_linha_com_lotacao_conhecida(self):
        linhas = [pessoa("RODRIGO", "Desistente", opcao="40000127", colocacao="1o PCD",
                         unidade="", lotacao=""),
                  pessoa("RODRIGO", "Desistente", opcao="40000127", colocacao="23o AC",
                         unidade="CPPSUL - Pec Sul", lotacao="Bage")]
        self.assertEqual(timeline.dedupe_pessoas(linhas)[0]["unidade"], "CPPSUL - Pec Sul")

    def test_colapso_mantem_o_status_terminal(self):
        linhas = [pessoa("EDIVANIO", "Convocado", opcao="40001565", colocacao="1o PCD"),
                  pessoa("EDIVANIO", "Desistente", opcao="40001565", colocacao="4o AC")]
        self.assertEqual(timeline.dedupe_pessoas(linhas)[0]["status"], "Desistente")

    def test_colapso_independe_da_ordem_das_linhas(self):
        a = pessoa("EDIVANIO", "Convocado", opcao="40001565", colocacao="1o PCD")
        b = pessoa("EDIVANIO", "Desistente", opcao="40001565", colocacao="4o AC")
        self.assertEqual(timeline.dedupe_pessoas([a, b]), timeline.dedupe_pessoas([b, a]))

    def test_duas_linhas_da_mesma_pessoa_nao_geram_evento_fantasma(self):
        linhas = [pessoa("EDIVANIO", "Desistente", opcao="40001565", colocacao="1o PCD"),
                  pessoa("EDIVANIO", "Desistente", opcao="40001565", colocacao="4o AC")]
        self.coletar(linhas)
        extras = self.coletar(list(reversed(linhas)))
        self.assertEqual(extras["changes"], [])


class TestMigracaoDeChave(TimelineTestCase):
    """O estado antigo usava opcao|colocacao|nome. Trocar de chave nao pode
    fazer 1.138 pessoas parecerem 'recem-convocadas'."""

    def test_estado_antigo_nao_gera_convocacao_nova(self):
        antigo = {"people": {"40001690|1O AC|ANA": "Contratado"},
                  "events": {"convocacoes": [], "contratacoes": []},
                  "changes": [], "changed_at": {"40001690|1O AC|ANA": "2026-01-01 10:00"},
                  "last_change": None}
        with open(timeline.STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(antigo, f)
        extras = self.coletar([pessoa("ANA", "Contratado")])
        self.assertEqual(extras["changes"], [])

    def test_migracao_preserva_o_alterado_em(self):
        antigo = {"people": {"40001690|1O AC|ANA": "Contratado"},
                  "events": {"convocacoes": [], "contratacoes": []},
                  "changes": [], "changed_at": {"40001690|1O AC|ANA": "2026-01-01 10:00"},
                  "last_change": None}
        with open(timeline.STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(antigo, f)
        extras = self.coletar([pessoa("ANA", "Contratado")])
        self.assertEqual(extras["changed_at"][timeline.norm_key("40001690", "ANA")],
                         "2026-01-01 10:00")


class TestSerieNaoDuplica(TimelineTestCase):
    """Cada pessoa entra UMA vez em cada serie -- senao o ritmo da linha do
    tempo infla toda vez que a fonte pisca."""

    def test_pessoa_so_entra_uma_vez_na_serie_de_contratacoes(self):
        self.coletar([pessoa("ANA", "Aceitou")])
        self.coletar([pessoa("ANA", "Contratado")])
        self.coletar([pessoa("ANA", "Contratado")])
        self.assertEqual(len(self.estado()["events"]["contratacoes"]), 1)

    def test_quem_some_e_volta_nao_conta_como_nova_convocacao(self):
        self.coletar([pessoa("ANA", "Convocado"), pessoa("BIA", "Convocado")])
        self.coletar([pessoa("BIA", "Convocado")])                  # ANA sumiu
        self.coletar([pessoa("ANA", "Convocado"), pessoa("BIA", "Convocado")])
        self.assertEqual(len(self.estado()["events"]["convocacoes"]), 0)

    def test_convocacao_nova_de_verdade_entra_na_serie(self):
        self.coletar([pessoa("ANA", "Convocado")])
        self.coletar([pessoa("ANA", "Convocado"), pessoa("BIA", "Convocado")])
        self.assertEqual(len(self.estado()["events"]["convocacoes"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
