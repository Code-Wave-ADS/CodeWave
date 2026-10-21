import sys
import types
import unittest

sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from agent import SteamAgent
from steam_countries import consultar_ranking_paises


class SteamCountriesTests(unittest.TestCase):
    def test_ranking_contains_source_and_caveat(self):
        resposta = consultar_ranking_paises()
        self.assertIn("Estados Unidos", resposta)
        self.assertIn("Brasil", resposta)
        self.assertIn("Fonte:", resposta)
        self.assertIn("não uma contagem oficial ou atual", resposta)

    def test_detects_country_ranking_question(self):
        self.assertTrue(SteamAgent._pergunta_sobre_ranking_de_paises("Quais países têm mais jogadores na Steam?"))
        self.assertTrue(SteamAgent._pergunta_sobre_ranking_de_paises("ranking de usuários por país da Steam"))

    def test_does_not_detect_unrelated_question(self):
        self.assertFalse(SteamAgent._pergunta_sobre_ranking_de_paises("Qual gênero tem mais jogos?"))


if __name__ == "__main__":
    unittest.main()
