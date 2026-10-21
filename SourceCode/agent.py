from __future__ import annotations

import json
from typing import Any

import ollama

from steam_analytics import AnalysisResult, SteamAnalytics
<<<<<<< HEAD
=======
from steam_countries import consultar_ranking_paises
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)


PLANNER_PROMPT = """
Você é o planejador de um agente de análise do dataset Steam.
Converta a pergunta do usuário em UMA instrução JSON para o Pandas.
<<<<<<< HEAD
Não responda a pergunta; apenas gere o plano.

Retorne SOMENTE JSON válido, sem markdown.
=======
Não responda a pergunta; apenas gere o plano. Retorne SOMENTE JSON válido, sem markdown.
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)

Schema:
{
  "scope": "steam_analysis" | "dev_support",
<<<<<<< HEAD
  "operation": "ranking" | "trend" | "summary" | "top_games",
=======
  "operation": "ranking" | "trend" | "summary" | "top_games" | "market",
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
  "dimension": "genres" | "platforms" | "categories" | "steamspy_tags" | "developer" | "publisher" | "release_year" | "name",
  "metric": "count" | "positive_ratings" | "negative_ratings" | "rating_ratio" | "average_playtime" | "median_playtime" | "price" | "owners_estimate" | "achievements",
  "aggregation": "count" | "sum" | "mean" | "median" | "max" | "min",
  "order": "desc" | "asc",
  "top_n": 10,
  "trend_years": 3,
<<<<<<< HEAD
  "filters": {
    "year_min": null,
    "year_max": null,
    "free_only": false,
    "paid_only": false,
    "price_min": null,
    "price_max": null,
    "genres": null,
    "platforms": null,
    "categories": null,
    "steamspy_tags": null,
    "developer": null,
    "publisher": null,
    "name": null
  }
}

Como interpretar:
- "qual gênero tem mais jogos?" => ranking, genres, count, count, desc.
- "qual plataforma é mais usada?" => ranking, platforms, count, count, desc.
- "qual gênero está em alta?" => trend, genres, count, count, desc.
- "qual gênero tem mais avaliações positivas?" => ranking, genres, positive_ratings, sum, desc.
- "quais gêneros têm mais donos estimados?" => ranking, genres, owners_estimate, sum, desc.
- "qual gênero é melhor avaliado?" => ranking, genres, rating_ratio, mean, desc.
- "qual é o preço médio?" => summary, name, price, mean.
- "quais jogos têm mais avaliações positivas?" => top_games, name, positive_ratings, max, desc.
- "quais jogos são mais caros?" => top_games, name, price, max, desc.
- "qual ano teve mais lançamentos?" => ranking, release_year, count, count, desc.
- Perguntas gerais de programação sem relação com a base => scope dev_support.

Prefira análise da base quando a pergunta falar de jogos, Steam, gênero, plataforma,
avaliações, preço, lançamentos, desenvolvedores, publishers, tags, donos ou tempo jogado.
""".strip()


ANSWER_PROMPT = """
Você é um bot de suporte para desenvolvedores que também analisa um dataset histórico da Steam.
Responda em português do Brasil.

Quando receber um RESULTADO CALCULADO PELO PANDAS:
- Use apenas os números fornecidos para afirmações sobre a base.
- Não invente estatísticas nem complemente com números externos.
- Diga claramente quando a conclusão vale apenas para o período do dataset.
- Responda primeiro de forma direta e depois explique em poucas linhas.
- Se houver ranking, mencione os primeiros colocados e seus valores.
- Para tendência, explique que "em alta" representa crescimento dentro da base e do período comparado.
- Se o resultado estiver vazio, diga que os dados não permitem responder.

Para dúvidas gerais de desenvolvimento, dê orientação prática e código pequeno quando útil.
""".strip()


class SteamAgent:
    def __init__(self, analytics: SteamAnalytics, model: str):
        self.analytics = analytics
        self.model = model

    def make_plan(self, question: str) -> dict[str, Any]:
        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": PLANNER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Pergunta: {question}\n\n"
                        f"Resumo da base carregada: {self.analytics.dataset_summary()}"
                    ),
                },
            ],
            format="json",
            options={"temperature": 0},
        )

        content = response.message.content.strip()
        try:
            plan = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"O Ollama retornou um plano JSON inválido: {content[:300]}") from exc

        if not isinstance(plan, dict):
            raise ValueError("O plano retornado pelo Ollama não é um objeto JSON.")
        return plan

    def answer_from_analysis(self, question: str, result: AnalysisResult) -> str:
        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": ANSWER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"PERGUNTA DO USUÁRIO:\n{question}\n\n"
                        f"{result.to_context()}"
                    ),
                },
            ],
            options={"temperature": 0.15},
        )
        return response.message.content.strip()

    def answer_dev_support(self, question: str) -> str:
        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": ANSWER_PROMPT},
                {"role": "user", "content": question},
            ],
            options={"temperature": 0.2},
        )
        return response.message.content.strip()

    def answer(self, question: str) -> tuple[str, dict[str, Any] | None]:
        plan = self.make_plan(question)
        if str(plan.get("scope", "steam_analysis")).strip().lower() == "dev_support":
            return self.answer_dev_support(question), plan

        result = self.analytics.analyze(plan)
        return self.answer_from_analysis(question, result), result.plan

"paid_only": false,
    "price_min": null,
    "price_max": null,
    "genres": null,
    "platforms": null,
    "categories": null,
    "steamspy_tags": null,
    "developer": null,
    "publisher": null,
    "name": null
=======
  "term": null,
  "filters": {
    "year_min": null, "year_max": null, "free_only": false, "paid_only": false,
    "price_min": null, "price_max": null, "genres": null, "platforms": null,
    "categories": null, "steamspy_tags": null, "developer": null,
    "publisher": null, "name": null
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
  }
}

Como interpretar:
- "qual gênero tem mais jogos?" => ranking, genres, count, count, desc.
- "qual plataforma é mais usada?" => ranking, platforms, count, count, desc.
- "qual gênero está em alta?" => trend, genres, count, count, desc.
- "qual gênero tem mais avaliações positivas?" => ranking, genres, positive_ratings, sum, desc.
- "qual gênero é melhor avaliado?" => ranking, genres, rating_ratio, mean, desc.
<<<<<<< HEAD
- "qual é o preço médio?" => summary, name, price, mean.
- "quais jogos têm mais avaliações positivas?" => top_games, name, positive_ratings, max, desc.
- "quais jogos são mais caros?" => top_games, name, price, max, desc.
=======
- "quais jogos têm mais avaliações positivas?" => top_games, name, positive_ratings, max, desc.
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
- "qual ano teve mais lançamentos?" => ranking, release_year, count, count, desc.
- "quantos jogadores existem para jogos de terror?" => operation market, term "terror".
- "qual o mercado de RPG?" => operation market, term "RPG".
- "estime o público de jogos cooperativos" => operation market, term "cooperativo".
<<<<<<< HEAD
- Perguntas gerais de programação sem relação com a base => scope dev_support.

Para perguntas sobre tamanho de mercado, quantidade de jogadores, público potencial ou número de donos de uma categoria/tag/gênero, use operation=market e preencha term somente com a categoria solicitada.
A base não contém jogadores ativos atuais nem pessoas únicas entre vários jogos; market deve usar owners estimados por título e a resposta precisa deixar essa limitação explícita.
Prefira análise da base quando a pergunta falar de jogos, Steam, gênero, plataforma, avaliações, preço, lançamentos, desenvolvedores, publishers, tags, donos ou tempo jogado.
""".strip()


ANSWER_PROMPT = """
Você é um bot de suporte para desenvolvedores que também analisa um dataset histórico da Steam.
Responda em português do Brasil.

Quando receber um RESULTADO CALCULADO PELO PANDAS:
- Use apenas os números fornecidos para afirmações sobre a base.
- Não invente estatísticas nem complemente com números externos.
- Diga claramente quando a conclusão vale apenas para o período do dataset.
- Responda primeiro de forma direta e depois explique em poucas linhas.
- Se houver ranking, mencione os primeiros colocados e seus valores.
- Para tendência, explique que "em alta" representa crescimento dentro da base e do período comparado.
- Para análises de mercado, deixe claro que owners são faixas estimadas de proprietários por jogo, não jogadores ativos nem pessoas únicas; a soma pode contar uma mesma pessoa em vários jogos. Apresente isso como indicador aproximado, não como número exato de mercado.
- Se o resultado estiver vazio, diga que os dados não permitem responder.

=======

Para tamanho de mercado ou público potencial de uma categoria/tag/gênero, use operation=market e preencha term apenas com a categoria solicitada. A base não contém jogadores ativos atuais nem pessoas únicas entre vários jogos; owners são faixas estimadas por título e a soma pode contar a mesma pessoa mais de uma vez.
Perguntas gerais de programação sem relação com a base => scope dev_support.
Prefira análise da base quando a pergunta falar de jogos, Steam, gênero, plataforma, avaliações, preço, lançamentos, desenvolvedores, publishers, tags, donos ou tempo jogado.
""".strip()

ANSWER_PROMPT = """
Você é um bot de suporte para desenvolvedores que também analisa um dataset histórico da Steam.
Responda em português do Brasil.
- Use apenas números fornecidos pela análise; não invente estatísticas.
- Diga quando a conclusão vale apenas para o período do dataset.
- Responda diretamente e depois explique brevemente.
- Em rankings, mencione os primeiros colocados e valores.
- Em tendências, explique que representam mudanças dentro da base e do período comparado.
- Em análises de mercado, owners são faixas estimadas de proprietários por jogo, não jogadores ativos nem pessoas únicas; a soma pode contar uma pessoa em vários jogos. Apresente como indicador aproximado.
- Se os dados forem insuficientes, diga isso claramente.
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
Para dúvidas gerais de desenvolvimento, dê orientação prática e código pequeno quando útil.
""".strip()


class SteamAgent:
    def __init__(self, analytics: SteamAnalytics, model: str):
        self.analytics = analytics
        self.model = model

    def make_plan(self, question: str) -> dict[str, Any]:
        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": PLANNER_PROMPT},
<<<<<<< HEAD
                {
                    "role": "user",
                    "content": (
                        f"Pergunta: {question}\n\n"
                        f"Resumo da base carregada: {self.analytics.dataset_summary()}"
                    ),
                },
=======
                {"role": "user", "content": f"Pergunta: {question}\n\nResumo da base carregada: {self.analytics.dataset_summary()}"},
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
            ],
            format="json",
            options={"temperature": 0},
        )
<<<<<<< HEAD

=======
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
        content = response.message.content.strip()
        try:
            plan = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"O Ollama retornou um plano JSON inválido: {content[:300]}") from exc
<<<<<<< HEAD

=======
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
        if not isinstance(plan, dict):
            raise ValueError("O plano retornado pelo Ollama não é um objeto JSON.")
        return plan

    def answer_from_analysis(self, question: str, result: AnalysisResult) -> str:
        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": ANSWER_PROMPT},
<<<<<<< HEAD
                {
                    "role": "user",
                    "content": (
                        f"PERGUNTA DO USUÁRIO:\n{question}\n\n"
                        f"{result.to_context()}"
                    ),
                },
=======
                {"role": "user", "content": f"PERGUNTA DO USUÁRIO:\n{question}\n\n{result.to_context()}"},
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
            ],
            options={"temperature": 0.15},
        )
        return response.message.content.strip()

    def answer_dev_support(self, question: str) -> str:
        response = ollama.chat(
            model=self.model,
<<<<<<< HEAD
            messages=[
                {"role": "system", "content": ANSWER_PROMPT},
                {"role": "user", "content": question},
            ],
=======
            messages=[{"role": "system", "content": ANSWER_PROMPT}, {"role": "user", "content": question}],
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
            options={"temperature": 0.2},
        )
        return response.message.content.strip()

<<<<<<< HEAD
    def answer(self, question: str) -> tuple[str, dict[str, Any] | None]:
        plan = self.make_plan(question)
        if str(plan.get("scope", "steam_analysis")).strip().lower() == "dev_support":
            return self.answer_dev_support(question), plan

=======
    @staticmethod
    def _pergunta_sobre_ranking_de_paises(question: str) -> bool:
        texto = question.casefold()
        termos_pais = ("país", "pais", "country", "countries", "região", "regiao")
        termos_contexto = ("steam", "jogador", "jogadores", "usuário", "usuarios", "usuários", "contas", "perfil", "perfis", "dono", "donos", "proprietário", "proprietarios", "proprietários")
        termos_ranking = ("mais", "ranking", "top", "maior", "maiores", "distribuição", "distribuicao", "por país", "por pais", "por região", "por regiao")
        tem_pais = any(termo in texto for termo in termos_pais)
        tem_contexto = any(termo in texto for termo in termos_contexto)
        tem_ranking = any(termo in texto for termo in termos_ranking)
        return tem_pais and (tem_contexto or tem_ranking) and ("steam" in texto or tem_contexto)

    def answer(self, question: str) -> tuple[str, dict[str, Any] | None]:
        if self._pergunta_sobre_ranking_de_paises(question):
            resposta = consultar_ranking_paises()
            plano = {
                "scope": "steam_country_ranking",
                "source": "World Population Review / referências históricas de perfis públicos Steam",
                "metric": "estimativa histórica de usuários por país",
            }
            return resposta, plano

        plan = self.make_plan(question)
        if str(plan.get("scope", "steam_analysis")).strip().lower() == "dev_support":
            return self.answer_dev_support(question), plan
>>>>>>> 5379140 (Vinculação dos principais idiomas ao bot)
        result = self.analytics.analyze(plan)
        return self.answer_from_analysis(question, result), result.plan
