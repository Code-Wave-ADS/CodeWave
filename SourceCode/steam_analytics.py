from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


MULTI_VALUE_COLUMNS = {
    "genres",
    "platforms",
    "categories",
    "steamspy_tags",
}

DIMENSION_ALIASES = {
    "genre": "genres",
    "genres": "genres",
    "platform": "platforms",
    "platforms": "platforms",
    "categoria": "categories",
    "categorias": "categories",
    "categories": "categories",
    "tag": "steamspy_tags",
    "tags": "steamspy_tags",
    "steamspy_tags": "steamspy_tags",
    "developer": "developer",
    "desenvolvedor": "developer",
    "publisher": "publisher",
    "publicadora": "publisher",
    "ano": "release_year",
    "release_year": "release_year",
    "jogo": "name",
    "name": "name",
}

ALLOWED_DIMENSIONS = {
    "genres",
    "platforms",
    "categories",
    "steamspy_tags",
    "developer",
    "publisher",
    "release_year",
    "name",
}

ALLOWED_METRICS = {
    "count",
    "positive_ratings",
    "negative_ratings",
    "rating_ratio",
    "average_playtime",
    "median_playtime",
    "price",
    "owners_estimate",
    "achievements",
}

ALLOWED_AGGREGATIONS = {"count", "sum", "mean", "median", "max", "min"}

ALLOWED_OPERATIONS = {"ranking", "trend", "summary", "top_games", "market", "seasonality", "age_rating"}

# NOVO: traduz o número do mês para o nome em português
MONTH_NAMES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

def _age_label(age: int) -> str:
    return "Livre" if age == 0 else f"+{age}"

def _text_key(value: Any) -> str:
    """Normaliza texto para comparar termos sem depender de acentos ou hífens."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().replace("-", " ").replace("_", " ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


CATEGORY_ALIASES = {
    "terror": "horror",
    "jogo de terror": "horror",
    "jogos de terror": "horror",
    "sobrevivencia": "survival",
    "acao": "action",
    "aventura": "adventure",
    "estrategia": "strategy",
    "simulacao": "simulation",
    "simulador": "simulation",
    "corrida": "racing",
    "esporte": "sports",
    "esportes": "sports",
    "independente": "indie",
    "jogo independente": "indie",
    "jogos independentes": "indie",
    "mundo aberto": "open world",
    "multiplayer": "multi player",
    "multijogador": "multi player",
    "jogador unico": "single player",
    "singleplayer": "single player",
    "cooperativo": "co op",
    "jogo cooperativo": "co op",
    "jogos cooperativos": "co op",
    "cartas": "card game",
    "jogos de cartas": "card game",
    "plataforma": "platformer",
    "jogos de plataforma": "platformer",
    "defesa de torres": "tower defense",
    "construcao de cidades": "city builder",
}


@dataclass
class AnalysisResult:
    title: str
    table: pd.DataFrame
    notes: list[str]
    plan: dict[str, Any]

    def to_context(self, max_rows: int = 20) -> str:
        shown = self.table.head(max_rows)
        table_text = shown.to_string(index=False)
        notes_text = "\n".join(f"- {note}" for note in self.notes) if self.notes else "- Nenhuma."
        return (
            f"ANÁLISE: {self.title}\n\n"
            f"PLANO EXECUTADO:\n{json.dumps(self.plan, ensure_ascii=False, indent=2)}\n\n"
            f"RESULTADO CALCULADO PELO PANDAS:\n{table_text}\n\n"
            f"OBSERVAÇÕES:\n{notes_text}"
        )


class SteamAnalytics:
    REQUIRED_COLUMNS = {
        "appid",
        "name",
        "release_date",
        "platforms",
        "genres",
        "positive_ratings",
        "negative_ratings",
        "average_playtime",
        "median_playtime",
        "owners",
        "price",
    }

    def __init__(self, csv_path: str | Path):
        self.path = Path(csv_path)
        if not self.path.exists():
            raise FileNotFoundError(
                f"Base Steam não encontrada: {self.path}. Coloque o steam.csv dentro da pasta data/."
            )

        self.df = pd.read_csv(self.path)
        missing = sorted(self.REQUIRED_COLUMNS - set(self.df.columns))
        if missing:
            raise ValueError(
                "O CSV não possui as colunas necessárias: " + ", ".join(missing)
            )

        self.df = self.df.copy()

        # Limpa gêneros que vêm no formato {'id': '1', 'description': 'Action'}
        self.df["genres"] = self.df["genres"].fillna("").astype(str).str.replace(
            r"\{'id':\s*'[^']*',\s*'description':\s*'([^']*)'\}",
            r"\1",
            regex=True
        )
        self.df["release_date"] = pd.to_datetime(self.df["release_date"], errors="coerce")
        self.df["release_year"] = self.df["release_date"].dt.year.astype("Int64")
        owner_bounds = self.df["owners"].apply(self._owners_bounds)
        self.df["owners_min"] = owner_bounds.apply(lambda bounds: bounds[0] if bounds else None)
        self.df["owners_max"] = owner_bounds.apply(lambda bounds: bounds[1] if bounds else None)
        self.df["owners_estimate"] = owner_bounds.apply(
            lambda bounds: (bounds[0] + bounds[1]) / 2 if bounds else None
        )

        ratings_total = self.df["positive_ratings"] + self.df["negative_ratings"]
        self.df["rating_ratio"] = (
            self.df["positive_ratings"] / ratings_total.where(ratings_total > 0)
        ) * 100

    @staticmethod
    def _owners_bounds(value: Any) -> tuple[float, float] | None:
        """Lê faixas como '0-20000' e '10,000 .. 20,000'."""
        if value is None or pd.isna(value):
            return None
        numbers = re.findall(r"\d[\d,]*", str(value))
        try:
            parsed = [float(number.replace(",", "")) for number in numbers[:2]]
            if len(parsed) >= 2:
                low, high = parsed[0], parsed[1]
                if high < low:
                    low, high = high, low
                return low, high
            if len(parsed) == 1:
                return parsed[0], parsed[0]
        except (TypeError, ValueError):
            pass
        return None

    @classmethod
    def _owners_midpoint(cls, value: Any) -> float | None:
        bounds = cls._owners_bounds(value)
        return (bounds[0] + bounds[1]) / 2 if bounds else None

    @property
    def row_count(self) -> int:
        return len(self.df)

    @property
    def min_year(self) -> int | None:
        years = self.df["release_year"].dropna()
        return int(years.min()) if not years.empty else None

    @property
    def max_year(self) -> int | None:
        years = self.df["release_year"].dropna()
        return int(years.max()) if not years.empty else None

    def dataset_summary(self) -> str:
        return (
            f"{self.row_count} jogos; período {self.min_year}-{self.max_year}; "
            f"colunas: {', '.join(self.df.columns)}"
        )

    def analyze(self, raw_plan: dict[str, Any]) -> AnalysisResult:
        plan = self._normalize_plan(raw_plan)
        operation = plan["operation"]

        if operation == "summary":
            return self._summary(plan)
        if operation == "trend":
            return self._trend(plan)
        if operation == "top_games":
            return self._top_games(plan)
        if operation == "ranking":
            return self._ranking(plan)
        if operation == "market":
            return self._market(plan)
        if operation == "seasonality":  # NOVO
            return self._seasonality(plan)
        if operation == "age_rating":  # NOVO
            return self._age_rating(plan)

        raise ValueError(f"Operação não suportada: {operation}")

    def _normalize_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(plan or {})

        operation = str(normalized.get("operation", "ranking")).strip().lower()
        if operation not in ALLOWED_OPERATIONS:
            operation = "ranking"
        normalized["operation"] = operation
        if "term" in normalized:
            normalized["term"] = str(normalized.get("term") or "").strip()

        dim_raw = str(normalized.get("dimension", "genres")).strip().lower()
        dimension = DIMENSION_ALIASES.get(dim_raw, dim_raw)
        if dimension not in ALLOWED_DIMENSIONS:
            dimension = "genres"
        normalized["dimension"] = dimension

        metric = str(normalized.get("metric", "count")).strip().lower()
        if metric not in ALLOWED_METRICS:
            metric = "count"
        normalized["metric"] = metric

        aggregation = str(normalized.get("aggregation", "count")).strip().lower()
        if metric == "count":
            aggregation = "count"
        elif aggregation not in ALLOWED_AGGREGATIONS:
            aggregation = "sum"
        normalized["aggregation"] = aggregation

        try:
            top_n = int(normalized.get("top_n", 10))
        except (TypeError, ValueError):
            top_n = 10
        normalized["top_n"] = min(max(top_n, 1), 25)

        order = str(normalized.get("order", "desc")).lower()
        normalized["order"] = "asc" if order == "asc" else "desc"

        filters = normalized.get("filters", {})
        normalized["filters"] = filters if isinstance(filters, dict) else {}

        trend_years = normalized.get("trend_years", 3)
        try:
            trend_years = int(trend_years)
        except (TypeError, ValueError):
            trend_years = 3
        normalized["trend_years"] = min(max(trend_years, 1), 10)

        return normalized

    def _filtered_df(self, filters: dict[str, Any]) -> pd.DataFrame:
        df = self.df.copy()

        year_min = filters.get("year_min")
        year_max = filters.get("year_max")
        if year_min is not None:
            try:
                df = df[df["release_year"] >= int(year_min)]
            except (TypeError, ValueError):
                pass
        if year_max is not None:
            try:
                df = df[df["release_year"] <= int(year_max)]
            except (TypeError, ValueError):
                pass

        if filters.get("free_only") is True:
            df = df[df["price"] == 0]
        if filters.get("paid_only") is True:
            df = df[df["price"] > 0]

        price_min = filters.get("price_min")
        price_max = filters.get("price_max")
        if price_min is not None:
            try:
                df = df[df["price"] >= float(price_min)]
            except (TypeError, ValueError):
                pass
        if price_max is not None:
            try:
                df = df[df["price"] <= float(price_max)]
            except (TypeError, ValueError):
                pass

        for column in ("genres", "platforms", "categories", "steamspy_tags"):
            value = filters.get(column)
            if value:
                needle = str(value).casefold()
                df = df[
                    df[column]
                    .fillna("")
                    .astype(str)
                    .str.casefold()
                    .str.split(";")
                    .apply(lambda parts: needle in [p.strip() for p in parts])
                ]

        for column in ("developer", "publisher", "name"):
            value = filters.get(column)
            if value:
                needle = str(value).casefold()
                df = df[df[column].fillna("").astype(str).str.casefold().str.contains(needle, regex=False)]

        return df

    def _explode_dimension(self, df: pd.DataFrame, dimension: str) -> pd.DataFrame:
        if dimension not in MULTI_VALUE_COLUMNS:
            return df

        expanded = df.copy()
        expanded[dimension] = expanded[dimension].fillna("").astype(str).str.split(";")
        expanded = expanded.explode(dimension)
        expanded[dimension] = expanded[dimension].astype(str).str.strip()
        return expanded[expanded[dimension] != ""]

    def _aggregate(self, df: pd.DataFrame, dimension: str, metric: str, aggregation: str) -> pd.DataFrame:
        df = self._explode_dimension(df, dimension)

        if metric == "count" or aggregation == "count":
            out = (
                df.groupby(dimension, dropna=True)
                .size()
                .reset_index(name="value")
            )
            return out

        if metric not in df.columns:
            raise ValueError(f"Métrica indisponível: {metric}")

        grouped = df.groupby(dimension, dropna=True)[metric]
        if aggregation == "sum":
            series = grouped.sum(min_count=1)
        elif aggregation == "mean":
            series = grouped.mean()
        elif aggregation == "median":
            series = grouped.median()
        elif aggregation == "max":
            series = grouped.max()
        elif aggregation == "min":
            series = grouped.min()
        else:
            series = grouped.sum(min_count=1)

        return series.reset_index(name="value")

    def _ranking(self, plan: dict[str, Any]) -> AnalysisResult:
        df = self._filtered_df(plan["filters"])
        result = self._aggregate(df, plan["dimension"], plan["metric"], plan["aggregation"])
        ascending = plan["order"] == "asc"
        result = result.sort_values("value", ascending=ascending).head(plan["top_n"]).reset_index(drop=True)
        result.insert(0, "posição", range(1, len(result) + 1))

        title = (
            f"Ranking por {plan['dimension']} usando {plan['aggregation']} de {plan['metric']}"
        )
        notes = [f"Foram considerados {len(df)} jogos após os filtros."]
        if plan["dimension"] in MULTI_VALUE_COLUMNS:
            notes.append(
                f"A coluna {plan['dimension']} pode conter vários valores por jogo; eles foram separados antes da contagem."
            )
        if plan["metric"] == "owners_estimate":
            notes.append("owners_estimate usa o ponto médio da faixa de owners do dataset.")
        if plan["metric"] == "rating_ratio":
            notes.append("rating_ratio = avaliações positivas / total de avaliações × 100.")

        return AnalysisResult(title, result, notes, plan)

    def _summary(self, plan: dict[str, Any]) -> AnalysisResult:
        df = self._filtered_df(plan["filters"])
        metric = plan["metric"]

        if metric == "count":
            value = len(df)
        else:
            series = pd.to_numeric(df[metric], errors="coerce").dropna()
            agg = plan["aggregation"]
            if series.empty:
                value = None
            elif agg == "sum":
                value = series.sum()
            elif agg == "median":
                value = series.median()
            elif agg == "max":
                value = series.max()
            elif agg == "min":
                value = series.min()
            else:
                value = series.mean()

        result = pd.DataFrame([{"metric": metric, "aggregation": plan["aggregation"], "value": value}])
        notes = [f"Foram considerados {len(df)} jogos após os filtros."]
        return AnalysisResult(f"Resumo de {metric}", result, notes, plan)

    def _top_games(self, plan: dict[str, Any]) -> AnalysisResult:
        df = self._filtered_df(plan["filters"]).copy()
        metric = plan["metric"]
        if metric == "count":
            metric = "positive_ratings"
            plan = dict(plan)
            plan["metric"] = metric
            plan["aggregation"] = "max"

        if metric not in df.columns:
            raise ValueError(f"Métrica indisponível para jogos: {metric}")

        ascending = plan["order"] == "asc"
        columns = ["name", metric, "genres", "platforms", "release_year", "price"]
        result = (
            df.sort_values(metric, ascending=ascending)
            .loc[:, [c for c in columns if c in df.columns]]
            .head(plan["top_n"])
            .reset_index(drop=True)
        )
        result.insert(0, "posição", range(1, len(result) + 1))
        return AnalysisResult(
            f"Jogos ordenados por {metric}",
            result,
            [f"Foram considerados {len(df)} jogos após os filtros."],
            plan,
        )

    # ------------------------------------------------------------------
    # NOVO: análise de sazonalidade (épocas/meses com mais vendas)
    # ------------------------------------------------------------------
    def _seasonality(self, plan: dict[str, Any]) -> AnalysisResult:
        """Descobre em quais meses do ano há mais vendas estimadas.

        A base não tem vendas por data. Usamos o mês de lançamento (release_date)
        e os owners estimados de cada jogo como indicador de vendas.
        """
        # 1) Aplica os filtros e descarta jogos sem data válida
        df = self._filtered_df(plan["filters"]).dropna(subset=["release_date"]).copy()

        colunas = [
            "posição", "mes", "nome_mes", "jogos_lancados",
            "owners_estimados_total", "media_por_jogo", "percentual",
        ]
        if df.empty:
            return AnalysisResult(
                "Sazonalidade sem dados",
                pd.DataFrame(columns=colunas),
                ["Nenhum registro disponível após os filtros."],
                plan,
            )

        # 2) Extrai o número do mês (1 a 12) da data de lançamento
        df["mes"] = df["release_date"].dt.month

        # 3) Agrupa por mês e calcula quantidade, total e média de owners
        mensal = (
            df.groupby("mes")
            .agg(
                jogos_lancados=("appid", "count"),
                owners_estimados_total=("owners_estimate", "sum"),
                media_por_jogo=("owners_estimate", "mean"),
            )
            .reset_index()
        )

        # 4) Calcula a participação de cada mês no total (em %)
        total = float(mensal["owners_estimados_total"].sum()) or 1.0
        mensal["percentual"] = (mensal["owners_estimados_total"] / total * 100).round(1)
        mensal["media_por_jogo"] = mensal["media_por_jogo"].round(0)

        # 5) Coloca o nome do mês ao lado do número
        mensal.insert(1, "nome_mes", mensal["mes"].map(MONTH_NAMES))

        # 6) Ordena (maior para menor por padrão) e limita ao top_n
        ascending = plan["order"] == "asc"
        resultado = (
            mensal.sort_values("owners_estimados_total", ascending=ascending)
            .head(plan["top_n"])
            .reset_index(drop=True)
        )
        resultado.insert(0, "posição", range(1, len(resultado) + 1))

        notes = [
            f"Foram considerados {len(df)} jogos com data de lançamento válida.",
            "A base não traz vendas por data: o mês é o do LANÇAMENTO do jogo e as vendas são "
            "estimadas pelos owners (ponto médio da faixa). Use como sinal de sazonalidade, não como vendas reais por mês.",
            "owners_estimados_total soma os owners dos jogos lançados no mês; media_por_jogo ajuda a ver "
            "se o mês é forte por ter muitos jogos ou por ter jogos que vendem bem.",
        ]
        return AnalysisResult("Sazonalidade: meses com mais vendas estimadas", resultado, notes, plan)

            # ------------------------------------------------------------------
    # NOVO: classificação etária (porcentagem de jogos por faixa etária)
    # ------------------------------------------------------------------
    def _age_rating(self, plan: dict[str, Any]) -> AnalysisResult:
        """Calcula a porcentagem de jogos em cada faixa etária (required_age)."""
        # 1) Aplica os filtros
        df = self._filtered_df(plan["filters"]).copy()
        total_filtrado = len(df)

        # 2) Se o steam.csv não tiver required_age, busca no arquivo de idades (junta pelo appid)
        usou_auxiliar = False
        if "required_age" not in df.columns:
            age_path = self.path.parent / "steam_required_age.csv"
            if not age_path.exists():
                raise FileNotFoundError(
                    f"Arquivo de faixas etárias não encontrado: {age_path}. "
                    "Coloque o steam_required_age.csv dentro da pasta data/."
                )
            ages = pd.read_csv(age_path, usecols=["appid", "required_age"])
            ages = ages.drop_duplicates(subset=["appid"])
            df = df.merge(ages, on="appid", how="left")
            usou_auxiliar = True
        df["required_age"] = pd.to_numeric(df["required_age"], errors="coerce")
        df = df.dropna(subset=["required_age"])

        colunas = ["posição", "faixa_etaria", "idade_minima", "jogos", "percentual"]
        if df.empty:
            return AnalysisResult(
                "Classificação etária sem dados",
                pd.DataFrame(columns=colunas),
                ["Nenhum registro disponível após os filtros."],
                plan,
            )

        # 3) Conta quantos jogos existem em cada idade mínima
        faixas = (
            df.groupby("required_age")
            .size()
            .reset_index(name="jogos")
            .rename(columns={"required_age": "idade_minima"})
        )
        faixas["idade_minima"] = faixas["idade_minima"].astype(int)

        # 4) Calcula a participação de cada faixa no total (em %)
        total = float(faixas["jogos"].sum()) or 1.0
        faixas["percentual"] = (faixas["jogos"] / total * 100).round(2)

        # 5) Coloca o nome da faixa ao lado da idade (0 vira "Livre")
        faixas.insert(0, "faixa_etaria", faixas["idade_minima"].map(_age_label))

        # 6) Ordena (maior para menor por padrão) e limita ao top_n
        ascending = plan["order"] == "asc"
        resultado = (
            faixas.sort_values("jogos", ascending=ascending)
            .head(plan["top_n"])
            .reset_index(drop=True)
        )
        resultado.insert(0, "posição", range(1, len(resultado) + 1))

        notes = [
            f"Foram considerados {len(df)} de {total_filtrado} jogos; os demais não têm required_age na base.",
            "required_age é a idade mínima para jogar informada na base; 0 significa sem restrição e aparece como Livre.",
            "O percentual é a participação de cada faixa no total de jogos considerados.",
        ]
        if usou_auxiliar:
            notes.append(
                "ATENÇÃO: a idade mínima vem de um arquivo auxiliar com menos jogos que a base principal; "
                "os percentuais valem apenas para os jogos que aparecem nos dois arquivos."
            )
        return AnalysisResult("Porcentagem de jogos por faixa etária", resultado, notes, plan)
    
    def _market(self, plan: dict[str, Any]) -> AnalysisResult:
        """Estima o público potencial de uma categoria usando owners por jogo.

        O CSV não identifica pessoas únicas nem jogadores ativos. Por isso, a soma de
        owners por título é apenas um indicador de alcance acumulado e pode contar
        a mesma pessoa em vários jogos.
        """
        requested_term = str(plan.get("term", "")).strip()
        if not requested_term:
            raise ValueError(
                "Informe uma categoria ou tag. Exemplo: /mercado Horror ou /mercado RPG."
            )

        # Remove prefixos comuns que podem vir de uma pergunta em linguagem natural.
        clean_term = _text_key(requested_term)
        for prefix in ("jogos de ", "jogo de ", "categoria ", "genero ", "tag ", "mercado de "):
            if clean_term.startswith(prefix):
                clean_term = clean_term[len(prefix):].strip()
        term = CATEGORY_ALIASES.get(clean_term, clean_term)
        if not term:
            raise ValueError("Não consegui identificar a categoria. Tente /mercado Horror ou /mercado RPG.")

        searchable_columns = [
            column for column in ("genres", "categories", "steamspy_tags")
            if column in self.df.columns
        ]
        if not searchable_columns:
            raise ValueError("A base não contém colunas de gêneros, categorias ou tags.")

        exact_masks = []
        partial_masks = []
        matched_columns: list[str] = []
        for column in searchable_columns:
            tokens = self.df[column].fillna("").astype(str).str.split(";")
            exact = tokens.apply(lambda parts: any(_text_key(part) == term for part in parts))
            partial = tokens.apply(lambda parts: any(term in _text_key(part) for part in parts))
            exact_masks.append(exact)
            partial_masks.append(partial)
            if bool(exact.any()):
                matched_columns.append(column)

        mask = exact_masks[0].copy()
        for other in exact_masks[1:]:
            mask = mask | other

        # Se não houver correspondência exata, permite uma busca parcial em tags compostas.
        if not bool(mask.any()):
            mask = partial_masks[0].copy()
            for other in partial_masks[1:]:
                mask = mask | other
            matched_columns = [
                column for column, partial in zip(searchable_columns, partial_masks)
                if bool(partial.any())
            ]

        games = self.df.loc[mask].copy()
        if "appid" in games.columns:
            games = games.drop_duplicates(subset=["appid"])

        plan["term"] = requested_term
        plan["normalized_term"] = term
        plan["matched_columns"] = matched_columns

        if games.empty:
            suggestions = self._popular_market_terms(searchable_columns, limit=12)
            return AnalysisResult(
                f"Mercado estimado: {requested_term}",
                pd.DataFrame(columns=["posição", "jogo", "owners_estimados_min", "owners_estimados_medio", "owners_estimados_max"]),
                [
                    f'Nenhum jogo correspondeu a "{requested_term}" nas colunas de gêneros, categorias ou tags.',
                    "Alguns termos existentes nesta base: " + ", ".join(suggestions),
                    "Tente o nome de uma tag em inglês ou use uma tradução comum, como /mercado terror (Horror).",
                ],
                plan,
            )

        owners_min = pd.to_numeric(games["owners_min"], errors="coerce").dropna()
        owners_mid = pd.to_numeric(games["owners_estimate"], errors="coerce").dropna()
        owners_max = pd.to_numeric(games["owners_max"], errors="coerce").dropna()

        low_sum = float(owners_min.sum()) if not owners_min.empty else 0.0
        mid_sum = float(owners_mid.sum()) if not owners_mid.empty else 0.0
        high_sum = float(owners_max.sum()) if not owners_max.empty else 0.0
        largest_title_lower_bound = float(owners_min.max()) if not owners_min.empty else 0.0
        average_mid = float(owners_mid.mean()) if not owners_mid.empty else 0.0
        median_mid = float(owners_mid.median()) if not owners_mid.empty else 0.0

        top_n = min(max(int(plan.get("top_n", 10)), 1), 20)
        visible_columns = [
            column for column in (
                "name", "owners_min", "owners_estimate", "owners_max",
                "genres", "categories", "steamspy_tags", "positive_ratings"
            ) if column in games.columns
        ]
        top_games = games.sort_values(
            "owners_estimate", ascending=False, na_position="last"
        ).loc[:, visible_columns].head(top_n).reset_index(drop=True)
        top_games = top_games.rename(columns={
            "name": "jogo",
            "owners_min": "owners_estimados_min",
            "owners_estimate": "owners_estimados_medio",
            "owners_max": "owners_estimados_max",
            "genres": "generos",
            "categories": "categorias_steam",
            "steamspy_tags": "tags",
            "positive_ratings": "avaliacoes_positivas",
        })
        top_games.insert(0, "posição", range(1, len(top_games) + 1))

        column_names = {
            "genres": "gêneros",
            "categories": "categorias Steam",
            "steamspy_tags": "tags SteamSpy",
        }
        matched_names = [column_names.get(column, column) for column in matched_columns]
        notes = [
            f'Termo pesquisado: "{requested_term}" (correspondência usada: "{term}").',
            f'Colunas com correspondências: {", ".join(matched_names) if matched_names else ", ".join(column_names.get(c, c) for c in searchable_columns)}.',
            f"Jogos distintos encontrados: {len(games):,}.",
            (
                "Soma estimada de proprietários por título (faixa inferior / ponto médio / faixa superior): "
                f"{low_sum:,.0f} / {mid_sum:,.0f} / {high_sum:,.0f}."
            ),
            (
                "Indicadores por jogo: média do ponto médio = "
                f"{average_mid:,.0f}; mediana = {median_mid:,.0f}."
            ),
            (
                "A base não informa quantas pessoas únicas possuem pelo menos um jogo da categoria. "
                f"Como referência muito aproximada, o maior limite inferior de um único título é {largest_title_lower_bound:,.0f}; "
                f"a soma dos limites superiores é {high_sum:,.0f}, mas esse máximo teórico pode contar a mesma pessoa várias vezes."
            ),
            (
                "IMPORTANTE: owners são estimativas de proprietários por jogo, não jogadores ativos agora nem usuários únicos. "
                "Somar títulos pode contar a mesma pessoa mais de uma vez. Use o resultado como sinal inicial de mercado, "
                "não como tamanho exato do público."
            ),
        ]

        return AnalysisResult(
            f"Estimativa de mercado para: {requested_term}",
            top_games,
            notes,
            plan,
        )

    def _popular_market_terms(self, columns: list[str], limit: int = 12) -> list[str]:
        counts: dict[str, int] = {}
        for column in columns:
            tokens = (
                self.df[column].fillna("").astype(str).str.split(";").explode().str.strip()
            )
            tokens = tokens[tokens != ""]
            for value, count in tokens.value_counts().head(limit * 2).items():
                counts[value] = counts.get(value, 0) + int(count)
        return [name for name, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]

    def _trend(self, plan: dict[str, Any]) -> AnalysisResult:
        dimension = plan["dimension"]
        if dimension == "release_year":
            dimension = "genres"
            plan = dict(plan)
            plan["dimension"] = dimension

        df = self._filtered_df(plan["filters"]).dropna(subset=["release_year"]).copy()
        if df.empty:
            return AnalysisResult(
                "Tendência sem dados",
                pd.DataFrame(columns=[dimension, "recent_share_pct", "previous_share_pct", "change_pp"]),
                ["Nenhum registro disponível após os filtros."],
                plan,
            )

        # Evita usar ano parcial no fim do dataset: o maior ano pode estar incompleto.
        max_year = int(df["release_year"].max())
        max_year_count = int((df["release_year"] == max_year).sum())
        prev_year_count = int((df["release_year"] == max_year - 1).sum())
        latest_full_year = max_year
        if prev_year_count > 0 and max_year_count < prev_year_count * 0.75:
            latest_full_year = max_year - 1

        n = plan["trend_years"]
        recent_start = latest_full_year - n + 1
        recent_end = latest_full_year
        previous_start = recent_start - n
        previous_end = recent_start - 1

        recent = df[df["release_year"].between(recent_start, recent_end)]
        previous = df[df["release_year"].between(previous_start, previous_end)]

        if recent.empty or previous.empty:
            raise ValueError(
                "Não há anos suficientes na base para comparar os dois períodos solicitados."
            )

        recent_counts = self._aggregate(recent, dimension, "count", "count").rename(columns={"value": "recent_count"})
        previous_counts = self._aggregate(previous, dimension, "count", "count").rename(columns={"value": "previous_count"})

        merged = recent_counts.merge(previous_counts, on=dimension, how="outer").fillna(0)
        recent_total = float(merged["recent_count"].sum()) or 1.0
        previous_total = float(merged["previous_count"].sum()) or 1.0
        merged["recent_share_pct"] = merged["recent_count"] / recent_total * 100
        merged["previous_share_pct"] = merged["previous_count"] / previous_total * 100
        merged["change_pp"] = merged["recent_share_pct"] - merged["previous_share_pct"]

        ascending = plan["order"] == "asc"
        result = (
            merged.sort_values("change_pp", ascending=ascending)
            .head(plan["top_n"])
            .reset_index(drop=True)
        )
        result.insert(0, "posição", range(1, len(result) + 1))

        notes = [
            f"Período recente: {recent_start}-{recent_end}; período anterior: {previous_start}-{previous_end}.",
            "Tendência é medida pela mudança de participação nos lançamentos, em pontos percentuais.",
            "Isso descreve tendência dentro do período do dataset, não o mercado atual fora da base.",
        ]
        if latest_full_year != max_year:
            notes.append(
                f"O ano {max_year} parece parcial na base e foi excluído da comparação principal."
            )

        return AnalysisResult(f"Tendência de {dimension}", result, notes, plan)