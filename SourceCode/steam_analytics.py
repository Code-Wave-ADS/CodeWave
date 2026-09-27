from __future__ import annotations

import json
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
        self.df["release_date"] = pd.to_datetime(self.df["release_date"], errors="coerce")
        self.df["release_year"] = self.df["release_date"].dt.year.astype("Int64")
        self.df["owners_estimate"] = self.df["owners"].apply(self._owners_midpoint)

        ratings_total = self.df["positive_ratings"] + self.df["negative_ratings"]
        self.df["rating_ratio"] = (
            self.df["positive_ratings"] / ratings_total.where(ratings_total > 0)
        ) * 100

    @staticmethod
    def _owners_midpoint(value: Any) -> float | None:
        try:
            text = str(value).strip().replace(",", "")
            if "-" not in text:
                return None
            low, high = text.split("-", 1)
            return (float(low) + float(high)) / 2
        except (TypeError, ValueError):
            return None

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

        raise ValueError(f"Operação não suportada: {operation}")

    def _normalize_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(plan or {})

        operation = str(normalized.get("operation", "ranking")).strip().lower()
        if operation not in {"ranking", "trend", "summary", "top_games"}:
            operation = "ranking"
        normalized["operation"] = operation

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
