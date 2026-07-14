import argparse
import itertools
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

mpl.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["CMU Serif", "DejaVu Serif", "Times New Roman", "serif"],
        "mathtext.fontset": "cm",
        "axes.labelsize": 11,
        "axes.titlesize": 13,
        "xtick.labelsize": 9,
        "ytick.labelsize": 10,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.05,
    }
)


EXPECTED_COLUMNS = ("Evaluator", "Method", "Coverage", "Precision", "Operability", "Acceptability")

METRIC_COLUMNS = ("Coverage", "Precision", "Operability", "Acceptability")

COLUMN_ALIASES = {
    "avaliador": "Evaluator",
    "agronomo": "Evaluator",
    "evaluator": "Evaluator",
    "metodo": "Method",
    "idspraying": "Method",
    "idcatacao": "Method",
    "method": "Method",
    "cobertura": "Coverage",
    "coberturaagronomica": "Coverage",
    "coverage": "Coverage",
    "precisao": "Precision",
    "excessodepulverizacao": "Precision",
    "precision": "Precision",
    "operacionalidade": "Operability",
    "operacionalidadedrone": "Operability",
    "operability": "Operability",
    "aceitabilidade": "Acceptability",
    "aceitabilidadegeral": "Acceptability",
    "acceptability": "Acceptability",
}


ZERO_LIKERT_METHOD_ID = "no-likert-data"

ZERO_LIKERT_METHOD_LABEL = "Likert data unavailable"


@dataclass(frozen=True, slots=True)
class MethodSummary:
    method_id: str

    method_label: str

    n_observations: int

    mean_score: float

    ci_low: float

    ci_high: float

    mean_rank: float

    n_ranked: int


@dataclass(frozen=True, slots=True)
class PairwiseSummary:
    comparison_type: str

    method_a_id: str

    method_a_label: str

    method_b_id: str

    method_b_label: str

    n_pairs: int

    n_permutations: int

    wins: int

    ties: int

    losses: int

    mean_difference: float

    p_value: float

    paired_evaluators: tuple[str, ...]


def _strip_accents(text: str) -> str:

    normalized = unicodedata.normalize("NFKD", text)

    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_column_name(name: object) -> str:

    text = _strip_accents(str(name)).lower().strip()

    return re.sub(r"[^a-z0-9]+", "", text)


def _normalize_method_id(name: object) -> str:

    text = _strip_accents(str(name)).lower().strip().replace("_", "-")

    text = re.sub(r"[^a-z0-9-]+", "-", text)

    text = re.sub(r"-{2,}", "-", text).strip("-")

    return text


def _format_method_label(method_id: str) -> str:

    normalized = _normalize_method_id(method_id)

    if normalized.startswith("spraying-"):
        normalized = normalized[len("spraying-") :]

    replacements = {
        "mrr": "MRR",
        "bp": "BP",
        "mops": "MOPS",
        "aabb": "AABB",
        "bcd": "BCD",
        "utm": "UTM",
        "wgs": "WGS",
    }

    parts = []

    for token in normalized.split("-"):
        parts.append(replacements.get(token, token.capitalize()))

    return " ".join(parts).strip() or method_id


def _read_input_table(input_path: Path) -> pd.DataFrame:

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    frame = pd.read_csv(input_path, sep=None, engine="python")

    rename_map: dict[str, str] = {}

    for column in frame.columns:
        normalized = _normalize_column_name(column)

        canonical = COLUMN_ALIASES.get(normalized)

        if canonical is not None:
            rename_map[column] = canonical

    frame = frame.rename(columns=rename_map)

    frame = frame.loc[:, EXPECTED_COLUMNS].copy()

    for column in METRIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["Evaluator"] = frame["Evaluator"].astype("string").str.strip()

    frame["Method"] = frame["Method"].astype("string").str.strip()

    frame = frame.dropna(subset=["Evaluator", "Method"])

    frame["Evaluator"] = frame["Evaluator"].astype(str)

    frame["Method"] = frame["Method"].astype(str)

    frame["overall_score"] = frame.loc[:, METRIC_COLUMNS].mean(axis=1, skipna=True)

    frame["metrics_used"] = frame.loc[:, METRIC_COLUMNS].notna().sum(axis=1)

    frame = frame.dropna(subset=["overall_score"]).reset_index(drop=True)

    return frame


def _empty_input_table() -> pd.DataFrame:

    columns = [
        "Evaluator",
        "Method",
        *METRIC_COLUMNS,
        "overall_score",
        "metrics_used",
    ]

    return pd.DataFrame(columns=columns)


def _bootstrap_mean_ci(
    values: Sequence[float], n_resamples: int, confidence_level: float, rng: np.random.Generator
) -> tuple[float, float, float, int]:

    sample = np.asarray(values, dtype=float)

    sample = sample[np.isfinite(sample)]

    n_observations = int(sample.size)

    if n_observations == 0:
        return float("nan"), float("nan"), float("nan"), 0

    mean_value = float(sample.mean())

    if n_observations < 2:
        return mean_value, mean_value, mean_value, n_observations

    bootstrap_result = stats.bootstrap(
        (sample,),
        np.mean,
        n_resamples=n_resamples,
        confidence_level=confidence_level,
        method="percentile",
        vectorized=False,
        random_state=rng,
    )

    ci_low = float(bootstrap_result.confidence_interval.low)

    ci_high = float(bootstrap_result.confidence_interval.high)

    return mean_value, ci_low, ci_high, n_observations


def _compute_method_summary(
    frame: pd.DataFrame, n_resamples: int, confidence_level: float, rng: np.random.Generator
) -> list[MethodSummary]:

    bootstrap_rows: list[dict[str, object]] = []

    for method_id, group in frame.groupby("Method", sort=True):
        mean_score, ci_low, ci_high, n_observations = _bootstrap_mean_ci(
            group["overall_score"].to_numpy(dtype=float),
            n_resamples=n_resamples,
            confidence_level=confidence_level,
            rng=rng,
        )

        bootstrap_rows.append(
            {
                "method_id": str(method_id),
                "method_label": _format_method_label(str(method_id)),
                "n_observations": n_observations,
                "mean_score": mean_score,
                "ci_low": ci_low,
                "ci_high": ci_high,
            }
        )

    rank_frame = frame.loc[:, ["Evaluator", "Method", "overall_score"]].copy()

    rank_frame = rank_frame[~rank_frame["Method"].isin(["spraying-mrr"])].copy()

    rank_frame["rank"] = rank_frame.groupby("Evaluator")["overall_score"].rank(
        method="average", ascending=False
    )

    rank_summary = (
        rank_frame.groupby("Method", sort=True)
        .agg(mean_rank=("rank", "mean"), n_ranked=("rank", "size"))
        .reset_index()
    )

    rank_lookup = {
        str(row["Method"]): (float(row["mean_rank"]), int(row["n_ranked"]))
        for _, row in rank_summary.iterrows()
    }

    summaries: list[MethodSummary] = []

    for row in sorted(
        bootstrap_rows, key=lambda item: (-float(item["mean_score"]), str(item["method_label"]))
    ):
        mean_rank, n_ranked = rank_lookup.get(str(row["method_id"]), (float("nan"), 0))

        summaries.append(
            MethodSummary(
                method_id=str(row["method_id"]),
                method_label=str(row["method_label"]),
                n_observations=int(row["n_observations"]),
                mean_score=float(row["mean_score"]),
                ci_low=float(row["ci_low"]),
                ci_high=float(row["ci_high"]),
                mean_rank=mean_rank,
                n_ranked=n_ranked,
            )
        )

    return summaries


def _paired_method_scores(frame: pd.DataFrame, method_a_id: str, method_b_id: str) -> pd.DataFrame:

    subset = frame.loc[
        frame["Method"].isin([method_a_id, method_b_id]), ["Evaluator", "Method", "overall_score"]
    ]

    pivot = subset.pivot_table(
        index="Evaluator", columns="Method", values="overall_score", aggfunc="mean"
    )

    if method_a_id not in pivot.columns:
        pivot[method_a_id] = np.nan

    if method_b_id not in pivot.columns:
        pivot[method_b_id] = np.nan

    paired = pivot.loc[:, [method_a_id, method_b_id]].dropna(how="any").copy()

    paired.index.name = "Evaluator"

    return paired.reset_index()


def _exact_paired_permutation_test(differences: Sequence[float]) -> tuple[float, float, int]:

    sample = np.asarray(differences, dtype=float)

    sample = sample[np.isfinite(sample)]

    n_pairs = int(sample.size)

    if n_pairs == 0:
        return float("nan"), float("nan"), 0

    observed = float(sample.mean())

    if n_pairs == 1:
        return observed, 1.0, 2

    signs = np.array(list(itertools.product((-1.0, 1.0), repeat=n_pairs)), dtype=float)

    permuted_statistics = (signs * sample).mean(axis=1)

    p_value = float(np.mean(np.abs(permuted_statistics) >= (abs(observed) - 1e-12)))

    return observed, p_value, int(2**n_pairs)


def _make_pairwise_summary(
    frame: pd.DataFrame, method_a_id: str, method_b_id: str, comparison_type: str
) -> PairwiseSummary:

    paired = _paired_method_scores(frame, method_a_id, method_b_id)

    if paired.empty:
        return PairwiseSummary(
            comparison_type=comparison_type,
            method_a_id=method_a_id,
            method_a_label=_format_method_label(method_a_id),
            method_b_id=method_b_id,
            method_b_label=_format_method_label(method_b_id),
            n_pairs=0,
            n_permutations=0,
            wins=0,
            ties=0,
            losses=0,
            mean_difference=float("nan"),
            p_value=float("nan"),
            paired_evaluators=(),
        )

    differences = paired[method_a_id].to_numpy(dtype=float) - paired[method_b_id].to_numpy(
        dtype=float
    )

    mean_difference, p_value, n_permutations = _exact_paired_permutation_test(differences)

    tolerance = 1e-12

    wins = int(np.sum(differences > tolerance))

    ties = int(np.sum(np.isclose(differences, 0.0, atol=tolerance)))

    losses = int(np.sum(differences < -tolerance))

    evaluators = tuple(str(value) for value in paired["Evaluator"].tolist())

    return PairwiseSummary(
        comparison_type=comparison_type,
        method_a_id=method_a_id,
        method_a_label=_format_method_label(method_a_id),
        method_b_id=method_b_id,
        method_b_label=_format_method_label(method_b_id),
        n_pairs=int(paired.shape[0]),
        n_permutations=n_permutations,
        wins=wins,
        ties=ties,
        losses=losses,
        mean_difference=mean_difference,
        p_value=p_value,
        paired_evaluators=evaluators,
    )


def _auto_pairwise_comparisons(
    frame: pd.DataFrame, baseline_methods: Sequence[str]
) -> list[PairwiseSummary]:

    normalized_to_original = {
        _normalize_method_id(method_id): str(method_id)
        for method_id in frame["Method"].dropna().unique().tolist()
    }

    summaries: list[PairwiseSummary] = []

    seen_pairs: set[tuple[str, str]] = set()

    def add_pair(method_a_id: str, method_b_id: str, comparison_type: str) -> None:

        pair_key = (method_a_id, method_b_id)

        if pair_key in seen_pairs:
            return

        seen_pairs.add(pair_key)

        summaries.append(_make_pairwise_summary(frame, method_a_id, method_b_id, comparison_type))

    for method_key, original_method_id in normalized_to_original.items():
        for target_key, target_original_id in normalized_to_original.items():
            if original_method_id == target_original_id:
                continue

            comparison_type = "mrr_vs_other"

            if target_key == method_key[:-4]:
                comparison_type = "mrr_vs_manual"

            elif target_key in [_normalize_method_id(bm) for bm in baseline_methods]:
                comparison_type = "mrr_vs_baseline"

            elif target_key.endswith("-mrr"):
                comparison_type = "mrr_vs_mrr"

            add_pair(original_method_id, target_original_id, comparison_type)

    return summaries


def _build_report_text(
    input_path: Path,
    frame: pd.DataFrame,
    method_summaries: Sequence[MethodSummary],
    pairwise_summaries: Sequence[PairwiseSummary],
) -> str:

    lines: list[str] = [
        "Likert Statistical Analysis - Blind Test",
        "=" * 40,
        f"Input file: {input_path.as_posix()}",
        f"Valid rows loaded: {len(frame)}",
        f"Unique evaluators: {frame['Evaluator'].nunique()}",
        f"Unique methods: {frame['Method'].nunique()}",
        "",
        f"{'Method':<28} {'n':>3} {'Mean':>8} {'95% CI Low':>15} {'95% CI High':>15} {'Mean Rank':>10}",
        "-" * 88,
    ]

    for summary in method_summaries:
        lines.append(
            f"{summary.method_label:<28} {summary.n_observations:>3d} {summary.mean_score:>8.3f} {summary.ci_low:>15.3f} {summary.ci_high:>15.3f} {summary.mean_rank:>10.3f}"
        )

    if pairwise_summaries:
        lines.extend(
            [
                "",
                "2) Wins / Ties / Losses and paired exact permutation test",
                f"{'Comparison':<36} {'n':>3} {'W':>3} {'D':>3} {'L':>3} {'Mean Diff':>11} {'exact p':>10} {'2^n':>6}",
                "-" * 100,
            ]
        )

        for summary in pairwise_summaries:
            comparison_label = f"{summary.method_a_label} vs {summary.method_b_label}"

            lines.append(
                f"{comparison_label:<36} {summary.n_pairs:>3d} {summary.wins:>3d} {summary.ties:>3d} {summary.losses:>3d} {summary.mean_difference:>11.3f} {summary.p_value:>10.4f} {summary.n_permutations:>6d}"
            )

    return "\n".join(lines)


def _summaries_to_csv_rows(
    method_summaries: Sequence[MethodSummary], pairwise_summaries: Sequence[PairwiseSummary]
) -> pd.DataFrame:

    rows: list[dict[str, object]] = []

    for summary in method_summaries:
        rows.append(
            {
                "section": "method_summary",
                "method_id": summary.method_id,
                "method_label": summary.method_label,
                "n": summary.n_observations,
                "mean_score": summary.mean_score,
                "ci_low": summary.ci_low,
                "ci_high": summary.ci_high,
                "mean_rank": summary.mean_rank,
                "comparison_type": "",
                "method_a_id": "",
                "method_a_label": "",
                "method_b_id": "",
                "method_b_label": "",
                "n_pairs": "",
                "n_permutations": "",
                "wins": "",
                "ties": "",
                "losses": "",
                "mean_difference": "",
                "p_value": "",
                "paired_evaluators": "",
            }
        )

    for summary in pairwise_summaries:
        rows.append(
            {
                "section": "paired",
                "method_id": "",
                "method_label": "",
                "n": "",
                "mean_score": "",
                "ci_low": "",
                "ci_high": "",
                "mean_rank": "",
                "comparison_type": summary.comparison_type,
                "method_a_id": summary.method_a_id,
                "method_a_label": summary.method_a_label,
                "method_b_id": summary.method_b_id,
                "method_b_label": summary.method_b_label,
                "n_pairs": summary.n_pairs,
                "n_permutations": summary.n_permutations,
                "wins": summary.wins,
                "ties": summary.ties,
                "losses": summary.losses,
                "mean_difference": summary.mean_difference,
                "p_value": summary.p_value,
                "paired_evaluators": "; ".join(summary.paired_evaluators),
            }
        )

    return pd.DataFrame(rows)


def _zero_method_summary() -> MethodSummary:

    return MethodSummary(
        method_id=ZERO_LIKERT_METHOD_ID,
        method_label=ZERO_LIKERT_METHOD_LABEL,
        n_observations=0,
        mean_score=0.0,
        ci_low=0.0,
        ci_high=0.0,
        mean_rank=0.0,
        n_ranked=0,
    )


def plot_heatmap(paired, output_name, title, figsize=(16, 8)):

    row_order = sorted(paired["method_a_label"].unique().tolist())

    col_order = sorted(paired["method_b_label"].unique().tolist())

    pivot_df = paired.pivot(
        index="method_a_label", columns="method_b_label", values="mean_difference"
    )

    pivot_df = pivot_df.reindex(index=row_order, columns=col_order)

    vmax = max(np.nanmax(np.abs(pivot_df.values)), 0.5)

    annot_df = pd.DataFrame("", index=pivot_df.index, columns=pivot_df.columns)

    for _, row in paired.iterrows():
        a = row["method_a_label"]

        b = row["method_b_label"]

        if a in annot_df.index and b in annot_df.columns:
            diff_str = f"{'+' if row['mean_difference'] > 0 else ''}{row['mean_difference']:.2f}"

            wins_losses_str = f"{int(row['wins'])}W, {int(row['ties'])}D, {int(row['losses'])}L"

            annot_df.loc[a, b] = f"{diff_str}\n({wins_losses_str})"

    fig, ax = plt.subplots(figsize=figsize)

    cmap = sns.diverging_palette(10, 220, s=80, l=55, as_cmap=True)

    sns.heatmap(
        pivot_df,
        annot=annot_df,
        fmt="",
        cmap=cmap,
        center=0,
        vmin=-vmax,
        vmax=vmax,
        linewidths=0.6,
        linecolor="white",
        ax=ax,
        square=False,
    )

    ax.set_facecolor("#f0f0f0")

    ax.set_yticklabels(pivot_df.index, rotation=0, fontweight="bold", fontstyle="italic")

    col_labels_formatted = [col.replace(" ", "\n") for col in pivot_df.columns]

    ax.set_xticklabels(col_labels_formatted, rotation=0, fontweight="bold", ha="center")

    ax.xaxis.tick_top()

    ax.xaxis.set_label_position("top")

    ax.set_xlabel("Compared Methods", fontweight="bold", labelpad=12)

    ax.set_ylabel("Methods", fontweight="bold", labelpad=12)

    ax.set_title(title, pad=28, fontweight="bold")

    plt.tight_layout()

    plt.savefig(f"{output_name}.png", dpi=300, bbox_inches="tight")

    plt.close()


def cli():

    parser = argparse.ArgumentParser()

    parser.add_argument("--input", type=Path, default=Path("data/input/likert_evaluations.csv"))

    parser.add_argument("--output-dir", type=Path, default=Path("data/output"))

    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    metrics_dir = args.output_dir / "metrics"

    plots_dir = args.output_dir / "plots"

    metrics_dir.mkdir(parents=True, exist_ok=True)

    plots_dir.mkdir(parents=True, exist_ok=True)

    if args.input.exists():
        frame = _read_input_table(args.input)

    else:
        print(f"Likert input not found: {args.input}. Generating zeroed statistics.")

        frame = _empty_input_table()

    rng = np.random.default_rng(42)

    if frame.empty:
        method_summaries = [_zero_method_summary()]

        pairwise_summaries = []

    else:
        method_summaries = _compute_method_summary(
            frame, n_resamples=10000, confidence_level=0.95, rng=rng
        )

        pairwise_summaries = _auto_pairwise_comparisons(
            frame, ["spraying-fixed-grid", "spraying-convex-hull"]
        )

    report_text = _build_report_text(args.input, frame, method_summaries, pairwise_summaries)

    csv_frame = _summaries_to_csv_rows(method_summaries, pairwise_summaries)

    csv_frame.to_csv(metrics_dir / "statistics.csv", index=False, encoding="utf-8")

    metrics_dir.joinpath("statistics.md").write_text(
        csv_frame.to_markdown(index=False), encoding="utf-8"
    )

    paired = csv_frame[csv_frame["section"] == "paired"].copy()

    if not paired.empty:
        paired["mean_difference"] = pd.to_numeric(paired["mean_difference"])

        paired["wins"] = pd.to_numeric(paired["wins"]).astype(int)

        paired["ties"] = pd.to_numeric(paired["ties"]).astype(int)

        paired["losses"] = pd.to_numeric(paired["losses"]).astype(int)

        all_paired = paired[
            (paired["method_a_label"] != "Generic MRR")
            & (paired["method_b_label"] != "Generic MRR")
        ]

        if not all_paired.empty:
            plot_heatmap(
                all_paired,
                str(plots_dir / "heatmap_all_vs_all"),
                "Complete Pairwise Confrontation Matrix: All vs All",
                figsize=(30, 30),
            )

    print(report_text)


if __name__ == "__main__":
    cli()
