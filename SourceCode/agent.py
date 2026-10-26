from __future__ import annotations
import pandas as pd
import json
from typing import Any
import os
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
    "operation": "ranking" | "trend" | "summary" | "top_games" | "market" | "seasonality" | "age_rating",
  "term": null,
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
- "quantos jogadores existem para jogos de terror?" => operation market, term "terror".
- "qual o mercado de RPG?" => operation market, term "RPG".
- "estime o público de jogos cooperativos" => operation market, term "cooperativo".
- "quais as épocas com maior número de vendas?" => operation seasonality, top_n 12, order desc.
- "em que mês devo fazer marketing?" => operation seasonality, top_n 12, order desc.
- "qual o melhor mês para divulgar um jogo?" => operation seasonality, top_n 12, order desc.
- "quais meses têm mais vendas de jogos de terror?" => operation seasonality, top_n 12, filters.steamspy_tags "Horror".
- "qual a porcentagem de jogos por faixa etária?" => operation age_rating, top_n 25, order desc.
- "quantos jogos são livres para todas as idades?" => operation age_rating, top_n 25, order desc.
- "qual a classificação etária dos jogos de terror?" => operation age_rating, top_n 25, order desc, filters.steamspy_tags "Horror".
- Perguntas gerais de programação sem relação com a base => scope dev_support.

Para perguntas sobre tamanho de mercado, quantidade de jogadores, público potencial ou número de donos de uma categoria/tag/gênero, use operation=market e preencha term somente com a categoria solicitada.
A base não contém jogadores ativos atuais nem pessoas únicas entre vários jogos; market deve usar owners estimados por título e a resposta precisa deixar essa limitação explícita.
Para perguntas sobre épocas, meses, estações, sazonalidade ou melhor momento para fazer marketing/divulgação, use operation=seasonality. Se o usuário citar uma categoria, coloque-a em filters (tags e categorias em inglês, como "Horror" ou "Indie").
Prefira análise da base quando a pergunta falar de jogos, Steam, gênero, plataforma, avaliações, preço, lançamentos, desenvolvedores, publishers, tags, donos ou tempo jogado.
Para perguntas sobre classificação indicativa, faixa etária, idade mínima ou público por idade, use operation=age_rating.
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
- Para sazonalidade, cite os meses do topo com o percentual de cada um e a quantidade de jogos lançados. Deixe claro que o mês é o de LANÇAMENTO dos jogos e que as vendas são estimadas por owners, então é um indicador de época forte e não vendas reais por mês. Pode sugerir planejar o marketing com antecedência para os meses do topo, sem inventar números.
- Para classificação etária, cite cada faixa com seu percentual e a quantidade de jogos, no formato "Livre - X%" e "+16 - Y%". Explique que Livre significa sem idade mínima (required_age = 0) e que a faixa vem do campo required_age. Se as observações indicarem cobertura parcial, deixe isso claro na resposta.
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
    
    for dirname, _, filenames in os.walk('SourceCode/data' ):
        for filename in filenames:
            print(os.path.join(dirname, filename))


gpuBenchMark = pd.read_csv('SourceCode/data/gpuMerged.csv')
rawDataSteam = pd.read_csv('SourceCode/data/gpuMerged.csv')

steamGPUsData = rawDataSteam.reset_index(drop = True)

if 'category' in steamGPUsData.columns:
        steamGPUsData = steamGPUsData[steamGPUsData['category'] == 'Video Card Description'].reset_index(drop = True)
else:
      raise KeyError("The 'categories column is missing from the dataset.")
     
print(steamGPUsData['name'])

gpuBenchMark['gpuName'] = gpuBenchMark['Brand'] + ' ' + gpuBenchMark['Model']
print(gpuBenchMark)