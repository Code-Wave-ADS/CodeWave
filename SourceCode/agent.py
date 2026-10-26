from __future__ import annotations
import pandas as pd
import json
import math
import re
import unicodedata
from typing import Any
import os
import ollama

from steam_analytics import AnalysisResult, SteamAnalytics
from steam_countries import consultar_ranking_paises


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


# Add-on guidance. Existing planning examples above are left unchanged.
PLANNER_PROMPT += """
- Para previsão de receita, lucro, margem, orçamento, ponto de equilíbrio ou jogos que vendem bem, use operation=profit_estimate, term igual ao gênero/tag identificado e dimension=genres ou steamspy_tags.
- "lucro medio de um jogo de RPG" => profit_estimate, term RPG, dimension genres, budget null.
- "lucro de jogo de quebra-cabeça" => profit_estimate, term Puzzle, dimension steamspy_tags.
- Inclua budget apenas se o usuário fornecer custos explicitamente; não invente orçamentos.
- Use platform_fee=0.30, paid_unit_share=0.85, price_realization=0.80, refund_rate=0.05, sales_tax_rate=0 salvo alteração explícita do usuário.
- Valores monetários devem estar na mesma unidade; nunca faça conversão implícita de R$ ou US$.
- O percentil 90 dos owners representa um cenário forte, não vendas confirmadas.
"""


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


ANSWER_PROMPT += """
- Para profit_estimate, indique amostra de jogos, preço mediano, faixa central, owners típicos e P90, e cenários de receita.
- Sem custos informados, NÃO estime lucro ou margem; peça orçamento na mesma unidade monetária do CSV.
- Com orçamento, apresente margem como simulação com premissas explícitas e taxa Steam de 30% (configurável).
- Owners não equivalem a vendas verificadas; o CSV não confirma moeda.
"""


def _normal_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in text if not unicodedata.combining(char))

def _parse_explicit_budget(question: str) -> tuple[float | None, bool]:
    """Extract only amounts explicitly tied to cost/budget language.

    Returns (amount, currency_problem). A BRL/USD-labelled cost must not be
    compared against the dataset's unspecified price currency.
    """
    q = _normal_text(question)
    pattern = (
        r"\b(?:orcamento|custos?|investimento|investir|investi|gastar|gastei|gasto|"
        r"gastos?|verba|budget)\b"
        r"(?:\s+(?:total|de|do|da|ate|estimado|previsto|foi|seria|no|valor))*"
        r"\s*(r\$|us\$|\$|eur|€)?\s*"
        r"(\d+(?:[.,]\d{3})*(?:[.,]\d{1,2})?)"
        r"(?:\s*(milhoes|milhao|mil|k))?\b"
    )
    match = re.search(pattern, q)
    if not match:
        return None, False
    if match.group(1):
        return None, True
    raw, suffix = match.group(2), match.group(3)
    if "." in raw and "," in raw:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        raw = raw.replace(",", "").replace(".", "")
    else:
        raw = raw.replace(",", ".")
    number = float(raw)
    factor = {"mil": 1_000, "k": 1_000, "milhao": 1_000_000, "milhoes": 1_000_000}.get(suffix, 1)
    return number * factor, False

def _looks_like_profit_question(question: str) -> bool:
    q = _normal_text(question)
    return bool(re.search(
        r"\b(?:lucro|lucratividade|margem|rentabilidade|receita|faturamento|"
        r"orcamento|rentavel|retorno financeiro|quanto (?:eu )?(?:ganharia|ganhar|faturaria|lucraria)|"
        r"vender bem|vender muito|vendas estimadas)\b",
        q,
    ))

def _format_number(value: float, decimals: int = 0) -> str:
    if value is None or not math.isfinite(float(value)):
        return "n/d"
    return f"{value:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")

def _format_profit_answer(result: AnalysisResult, currency_warning: bool = False) -> str:
    """Fixed, calculation-only response: no numeric hallucinations, no Ollama call."""
    rows = result.table.set_index("scenario")
    typical = rows.loc["typical_p50"]
    strong = rows.loc["sells_well_p90"]
    breakout = rows.loc["breakout_p95"]
    term = result.plan["term"]
    category = "gênero" if result.plan["dimension"] == "genres" else "tag"
    budget = result.plan.get("budget")
    year_min = result.plan["filters"].get("year_min")
    year_max = result.plan["filters"].get("year_max")
    lines = [
        f"Estimativa para jogos com {category} {term} (Steam, lançamentos de {year_min} a {year_max}):",
        f"• Amostra: {_format_number(int(strong['cohort_games']))} jogos pagos.",
        f"• Preço mediano: {_format_number(strong['genre_median_list_price'], 2)} por cópia; faixa central: {_format_number(strong['genre_price_q25'], 2)}–{_format_number(strong['genre_price_q75'], 2)}.",
        f"• Owners estimados: média {_format_number(strong['mean_estimated_owners'])}, mediana {_format_number(typical['owners_midpoint_proxy'])}; 'vende bem' (P90) {_format_number(strong['owners_midpoint_proxy'])}.",
        "",
    ]
    if budget is None:
        lines += [
            "Receita estimada para o desenvolvedor (após deduções presumidas):",
            f"• Cenário típico (P50): {_format_number(typical['developer_revenue_proxy'], 2)}",
            f"• Se vender bem (P90): {_format_number(strong['developer_revenue_proxy'], 2)}",
            f"• Excelente desempenho (P95): {_format_number(breakout['developer_revenue_proxy'], 2)}",
            "",
            "Lucro e margem NÃO podem ser calculados sem os custos. Qual é o seu orçamento total de desenvolvimento + marketing (na mesma unidade monetária do CSV)?",
        ]
    else:
        lines += [
            f"Com orçamento total de {_format_number(budget, 2)}:",
            f"• Típico (P50): lucro {_format_number(typical['profit_proxy'], 2)}; margem {_format_number(typical['operating_margin_percent'], 2)}%.",
            f"• Se vender bem (P90): lucro {_format_number(strong['profit_proxy'], 2)}; margem {_format_number(strong['operating_margin_percent'], 2)}%.",
            f"• Excelente desempenho (P95): lucro {_format_number(breakout['profit_proxy'], 2)}; margem {_format_number(breakout['operating_margin_percent'], 2)}%.",
        ]
    if currency_warning:
        lines += ["", "Você informou custos com uma moeda explícita. Não os subtraí: a moeda de preços no CSV não está identificada e não fiz conversão implícita."]
    paid = result.plan["paid_unit_share"]
    realized = result.plan["price_realization"]
    refunds = result.plan["refund_rate"]
    steam_fee = result.plan["platform_fee"]
    tax = result.plan["sales_tax_rate"]
    lines += [
        "",
        f"Hipóteses: {paid:.0%} dos owners representariam vendas pagas; preço realizado {realized:.0%} da tabela; "
        f"{refunds:.0%} de reembolsos/perdas; {steam_fee:.0%} de taxa Steam; {tax:.0%} de tributos sobre vendas.",
        "ATENÇÃO: owners são estimativas históricas por jogo, NÃO vendas verificadas, jogadores ativos ou previsão garantida. Valores na unidade monetária não identificada do CSV; sem impostos sobre lucro, royalties ou despesas não orçadas.",
    ]
    return "\n".join(lines)

class SteamAgent:

    @staticmethod
    def _pergunta_sobre_ranking_de_paises(question: str) -> bool:
        """Identify country rankings, provided by the existing country dataset.

        Kept deliberately narrow so it does not interfere with genre rankings or
        game profitability questions.
        """
        normalized = _normal_text(question)
        return all((
            re.search(r"\bsteam\b", normalized),
            re.search(r"\b(?:pais|paises)\b", normalized),
            re.search(r"\b(?:jogadores|usuarios|contas)\b", normalized),
            re.search(r"\b(?:ranking|mais|maiores|top)\b", normalized),
        ))

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
        # Add-on: historical Steam country ranking, without interfering with other questions.
        if self._pergunta_sobre_ranking_de_paises(question):
            return consultar_ranking_paises(), {"operation": "country_ranking"}

        # Fast path: interpret common natural-language profitability questions locally.
        if _looks_like_profit_question(question):
            category = self.analytics.resolve_profit_category(question, from_question=True)
            if category:
                budget, wrong_currency = _parse_explicit_budget(question)
                profit_plan = {
                    "scope": "steam_analysis", "operation": "profit_estimate",
                    "term": category[0], "dimension": category[1], "budget": budget,
                }
                profit_result = self.analytics.analyze(profit_plan)
                return _format_profit_answer(profit_result, wrong_currency), profit_result.plan

        plan = self.make_plan(question)
        if str(plan.get("scope", "steam_analysis")).strip().lower() == "dev_support":
            return self.answer_dev_support(question), plan

        # Add-on: route unfamiliar profit wording through Ollama's planner.
        if plan.get("operation") == "profit_estimate":
            category = self.analytics.resolve_profit_category(str(plan.get("term") or ""))
            if category is None:
                return "Informe um gênero ou tag Steam, por exemplo RPG, Adventure ou Puzzle.", plan
            plan["term"], plan["dimension"] = category
            budget, wrong_currency = _parse_explicit_budget(question)
            plan["budget"] = budget  # Ignore any budget hallucinated by the LLM.
            result = self.analytics.analyze(plan)
            return _format_profit_answer(result, wrong_currency), result.plan

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