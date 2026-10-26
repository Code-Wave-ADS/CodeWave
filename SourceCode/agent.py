from __future__ import annotations

import json
from typing import Any

import ollama

from steam_analytics import AnalysisResult, SteamAnalytics


PLANNER_PROMPT = """
Você é o planejador de um agente de análise do dataset Steam.
Converta a pergunta do usuário em UMA instrução JSON para o Pandas.
Não responda a pergunta; apenas gere o plano.

Retorne SOMENTE JSON válido, sem markdown.

Schema:
{
  "scope": "steam_analysis" | "dev_support",
  "operation": "ranking" | "trend" | "summary" | "top_games" | "controller_support",
  "dimension": "genres" | "platforms" | "categories" | "steamspy_tags" | "developer" | "publisher" | "release_year" | "name",
  "metric": "count" | "positive_ratings" | "negative_ratings" | "rating_ratio" | "average_playtime" | "median_playtime" | "price" | "owners_estimate" | "achievements",
  "aggregation": "count" | "sum" | "mean" | "median" | "max" | "min",
  "order": "desc" | "asc",
  "top_n": 10,
  "trend_years": 3,
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
- "quais gêneros têm mais suporte a controle?" => controller_support.
- "qual a porcentagem de jogos com suporte completo ou parcial a controle por gênero?" => controller_support.


Prefira análise da base quando a pergunta falar de jogos, Steam, gênero, plataforma,
avaliações, preço, lançamentos, desenvolvedores, publishers, tags, donos ou tempo jogado.
""".strip()


ANSWER_PROMPT = """
Você é um bot de suporte para desenvolvedores que também analisa
um dataset histórico da Steam.
Responda em português do Brasil.

REGRAS OBRIGATÓRIAS:
- Use apenas os dados fornecidos pelo resultado da análise.
- Nunca invente estatísticas, valores, rankings ou conclusões.
- Não confunda a ordem em que os dados aparecem com um ranking.
- Se os dados não estiverem ordenados pela métrica solicitada,
  não apresente um Top N como se estivesse correto.
- Não diga que um gênero tem o maior percentual sem comparar
  os valores disponíveis.
- Não afirme que gêneros têm suporte alto ou baixo sem
  comparação sustentada pelos dados.
- Se não conseguir determinar o ranking corretamente,
  informe essa limitação.
- Responda primeiro de forma direta e depois explique brevemente.
- Mantenha a resposta curta.

REGRAS PARA controller_support:
- Os percentuais representam jogos da base, não jogadores
  que usariam controle.
- "Não identificado" significa que o suporte não foi
  identificado nos dados, não que o jogo não tem suporte.
- Suporte completo ou parcial não comprova, por si só,
  acessibilidade.
- Nunca misture os percentuais de suporte completo e parcial.
- Ao responder um Top N, use a métrica pedida e ordene
  do maior para o menor quando solicitado.
- Não invente gêneros ou percentuais ausentes.

Para dúvidas gerais de desenvolvimento, dê orientação prática
e código pequeno quando útil.
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
