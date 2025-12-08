"""Procesa resultados de FIO y genera análisis estructurado en 3 carpetas:
- baseline: análisis línea base VM
- ml: análisis red neuronal
- comparativa: análisis comparativo

Solo genera gráficos más descriptivos.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

BASE_DIR = Path(__file__).resolve().parents[1]
BASELINE_RESULTS = BASE_DIR / "experiments" / "results_baseline"
ML_RESULTS = BASE_DIR / "experiments" / "results_ml"
OUTPUT_BASE = BASE_DIR / "analisis"

sns.set_theme(style="whitegrid", palette="husl")

WORKLOAD_ORDER = ["seq", "rand", "mix"]
SIZE_ORDER = ["100M", "500M", "1G"]


def parse_size_mb(size_label: str) -> float:
    """Convierte 100M o 1G a MB."""
    if size_label.lower().endswith("m"):
        return float(size_label[:-1])
    if size_label.lower().endswith("g"):
        return float(size_label[:-1]) * 1024
    raise ValueError(f"Tamaño no reconocido: {size_label}")


def extract_percentile(clat: Dict, key: str) -> float:
    percentiles = clat.get("percentile", {}) if clat else {}
    value = percentiles.get(key)
    return value / 1_000_000 if value is not None else np.nan


def load_records(results_root: Path, label: str = None) -> pd.DataFrame:
    """Carga registros desde JSON de FIO."""
    records = []
    for path in sorted(results_root.glob("*/*/result_*_run*.json")):
        workload = path.parent.parent.name
        size_label = path.parent.name
        run = int(path.stem.split("run")[-1])

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        job = data["jobs"][0]

        for op in ("read", "write"):
            stats = job.get(op, {})
            io_bytes = stats.get("io_bytes", 0)
            if io_bytes <= 0:
                continue

            clat = stats.get("clat_ns", {})
            record = {
                "workload": workload,
                "size_label": size_label,
                "size_mb": parse_size_mb(size_label),
                "run": run,
                "op": op,
                "bw_MB_s": stats.get("bw_bytes", 0) / 1_000_000,
                "iops": stats.get("iops", np.nan),
                "p99_ms": extract_percentile(clat, "99.000000"),
                "lat_mean_ms": stats.get("lat_ns", {}).get("mean", np.nan) / 1_000_000,
            }
            if label:
                record["implementation"] = label
            records.append(record)

    df = pd.DataFrame.from_records(records)
    if not df.empty:
        df["workload"] = pd.Categorical(df["workload"], categories=WORKLOAD_ORDER, ordered=True)
        df["size_label"] = pd.Categorical(df["size_label"], categories=SIZE_ORDER, ordered=True)
        df = df.sort_values(["workload", "size_mb", "run", "op"])
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """Crea resumen agregado por workload/op/tamaño."""
    return (
        df.groupby(["workload", "op", "size_label"], observed=True)
        .agg(
            runs=("run", "count"),
            bw_MB_s_mean=("bw_MB_s", "mean"),
            bw_MB_s_std=("bw_MB_s", "std"),
            iops_mean=("iops", "mean"),
            p99_ms_mean=("p99_ms", "mean"),
        )
        .reset_index()
        .sort_values(["workload", "op", "size_label"])
    )


def process_baseline():
    """Procesa baseline VM."""
    print("\n📊 Procesando Baseline VM...")
    df = load_records(BASELINE_RESULTS)
    if df.empty:
        raise SystemExit("No se encontraron resultados en results_baseline")

    summary = summarize(df)
    output_dir = OUTPUT_BASE / "baseline"
    output_dir.mkdir(exist_ok=True)

    # Guardar datos
    df.to_csv(output_dir / "resultados_detalle.csv", index=False)
    summary.to_csv(output_dir / "resumen_metricas.csv", index=False)

    # Gráficos (solo descriptivos)
    _plot_throughput(df, output_dir, "baseline", "Baseline (VM)")
    _plot_latency(df, output_dir, "baseline", "Baseline (VM)")

    # Reporte
    _generate_report(df, summary, output_dir, "reporte_baseline.md", "Baseline VM")

    print(f"✓ Baseline completado en {output_dir}")
    return df, summary


def process_ml():
    """Procesa ML."""
    print("\n🧠 Procesando ML (Red Neuronal)...")
    df = load_records(ML_RESULTS)
    if df.empty:
        raise SystemExit("No se encontraron resultados en results_ml")

    summary = summarize(df)
    output_dir = OUTPUT_BASE / "ml"
    output_dir.mkdir(exist_ok=True)

    # Guardar datos
    df.to_csv(output_dir / "resultados_detalle.csv", index=False)
    summary.to_csv(output_dir / "resumen_metricas.csv", index=False)

    # Gráficos (solo descriptivos)
    _plot_throughput(df, output_dir, "ml", "ML (Red Neuronal)")
    _plot_latency(df, output_dir, "ml", "ML (Red Neuronal)")

    # Reporte
    _generate_report(df, summary, output_dir, "reporte_ml.md", "ML (Red Neuronal)")

    print(f"✓ ML completado en {output_dir}")
    return df, summary


def process_comparative(df_baseline: pd.DataFrame, df_ml: pd.DataFrame):
    """Crea análisis comparativo."""
    print("\n⚖️  Procesando Análisis Comparativo...")
    
    # Agregar etiqueta de implementación
    df_baseline["implementation"] = "Baseline (VM)"
    df_ml["implementation"] = "ML (Red Neuronal)"
    df_combined = pd.concat([df_baseline, df_ml], ignore_index=True)

    summary_combined = (
        df_combined.groupby(["implementation", "workload", "op", "size_label"], observed=True)
        .agg(
            bw_MB_s_mean=("bw_MB_s", "mean"),
            bw_MB_s_std=("bw_MB_s", "std"),
            p99_ms_mean=("p99_ms", "mean"),
        )
        .reset_index()
    )

    output_dir = OUTPUT_BASE / "comparativa"
    output_dir.mkdir(exist_ok=True)

    # Guardar datos
    df_combined.to_csv(output_dir / "resultados_combinados.csv", index=False)
    summary_combined.to_csv(output_dir / "comparativa_metricas.csv", index=False)

    # Gráfico comparativo (lado a lado)
    _plot_comparison(df_combined, output_dir)

    # Reporte comparativo
    _generate_comparative_report(summary_combined, output_dir)

    print(f"✓ Comparativa completado en {output_dir}")


def _plot_throughput(df: pd.DataFrame, output_dir: Path, prefix: str, title_suffix: str) -> None:
    """Gráfico de throughput de lectura (solo)."""
    (output_dir).mkdir(exist_ok=True)
    data = df[df["op"] == "read"].copy()

    plt.figure(figsize=(10, 5))
    ax = sns.barplot(
        data=data,
        x="workload",
        y="bw_MB_s",
        hue="size_label",
        errorbar="sd",
    )
    ax.set_title(f"Throughput de Lectura - {title_suffix}", fontsize=14, fontweight="bold")
    ax.set_xlabel("Patrón de Acceso", fontsize=11)
    ax.set_ylabel("Throughput (MB/s)", fontsize=11)
    ax.legend(title="Tamaño", loc="best")
    plt.tight_layout()
    plt.savefig(output_dir / "throughput_lectura.png", dpi=150, bbox_inches="tight")
    plt.close()


def _plot_latency(df: pd.DataFrame, output_dir: Path, prefix: str, title_suffix: str) -> None:
    """Gráfico de latencia p99 de lectura (solo)."""
    (output_dir).mkdir(exist_ok=True)
    data = df[df["op"] == "read"].copy()

    plt.figure(figsize=(10, 5))
    ax = sns.barplot(
        data=data,
        x="workload",
        y="p99_ms",
        hue="size_label",
        errorbar="sd",
    )
    ax.set_title(f"Latencia p99 de Lectura - {title_suffix}", fontsize=14, fontweight="bold")
    ax.set_xlabel("Patrón de Acceso", fontsize=11)
    ax.set_ylabel("Latencia p99 (ms)", fontsize=11)
    ax.legend(title="Tamaño", loc="best")
    plt.tight_layout()
    plt.savefig(output_dir / "latencia_p99.png", dpi=150, bbox_inches="tight")
    plt.close()


def _plot_comparison(df: pd.DataFrame, output_dir: Path) -> None:
    """Gráfico de comparación side-by-side."""
    (output_dir).mkdir(exist_ok=True)
    data = df[df["op"] == "read"].copy()

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Throughput
    ax = axes[0]
    sns.barplot(
        data=data,
        x="workload",
        y="bw_MB_s",
        hue="implementation",
        errorbar="sd",
        ax=ax,
    )
    ax.set_title("Throughput de Lectura", fontsize=12, fontweight="bold")
    ax.set_xlabel("Patrón de Acceso")
    ax.set_ylabel("Throughput (MB/s)")

    # Latencia
    ax = axes[1]
    sns.barplot(
        data=data,
        x="workload",
        y="p99_ms",
        hue="implementation",
        errorbar="sd",
        ax=ax,
    )
    ax.set_title("Latencia p99 de Lectura", fontsize=12, fontweight="bold")
    ax.set_xlabel("Patrón de Acceso")
    ax.set_ylabel("Latencia p99 (ms)")

    plt.tight_layout()
    plt.savefig(output_dir / "comparativa_metricas.png", dpi=150, bbox_inches="tight")
    plt.close()


def _generate_report(df: pd.DataFrame, summary: pd.DataFrame, output_dir: Path, filename: str, title: str) -> None:
    """Genera reporte markdown."""
    read_summary = summary[summary["op"] == "read"].copy()

    best_read = read_summary.sort_values("bw_MB_s_mean", ascending=False).iloc[0]
    fastest_p99 = read_summary.sort_values("p99_ms_mean").iloc[0]

    lines = [
        f"# Reporte de Análisis - {title}",
        "",
        "## Resumen Ejecutivo",
        f"- **Mayor throughput de lectura**: {best_read['bw_MB_s_mean']:.1f} MB/s en {best_read['workload'].upper()} {best_read['size_label']}",
        f"- **Mejor latencia p99**: {fastest_p99['p99_ms_mean']:.3f} ms en {fastest_p99['workload'].upper()} {fastest_p99['size_label']}",
        "",
        "## Métricas por Patrón de Acceso (Lectura)",
    ]

    for workload in WORKLOAD_ORDER:
        lines.append(f"\n### {workload.upper()}")
        subset = read_summary[read_summary["workload"] == workload]
        for _, row in subset.iterrows():
            lines.append(
                f"- **{row['size_label']}**: {row['bw_MB_s_mean']:.1f} ± {row['bw_MB_s_std']:.1f} MB/s, "
                f"p99={row['p99_ms_mean']:.3f} ms"
            )

    lines.extend([
        "",
        "## Archivos Generados",
        "- `resultados_detalle.csv`: métricas por corrida",
        "- `resumen_metricas.csv`: agregados por patrón/tamaño",
        "- `throughput_lectura.png`: gráfico de throughput",
        "- `latencia_p99.png`: gráfico de latencia",
    ])

    output_dir.joinpath(filename).write_text("\n".join(lines), encoding="utf-8")


def _generate_comparative_report(summary: pd.DataFrame, output_dir: Path) -> None:
    """Genera reporte comparativo."""
    lines = [
        "# Análisis Comparativo: Baseline (VM) vs ML (Red Neuronal)",
        "",
        "## Resumen Ejecutivo",
    ]

    read_summary = summary[summary["op"] == "read"]
    baseline_avg = read_summary[read_summary["implementation"] == "Baseline (VM)"]["bw_MB_s_mean"].mean()
    ml_avg = read_summary[read_summary["implementation"] == "ML (Red Neuronal)"]["bw_MB_s_mean"].mean()

    delta = ((ml_avg - baseline_avg) / baseline_avg * 100) if baseline_avg else 0
    winner = "**ML**" if delta > 0 else "**Baseline**"

    lines.extend([
        f"- **Throughput promedio lectura**: Baseline {baseline_avg:.1f} MB/s vs ML {ml_avg:.1f} MB/s ({delta:+.1f}%)",
        f"- **Ganador general**: {winner}",
        "",
        "## Comparativa por Patrón y Tamaño (Lectura)",
    ])

    for workload in WORKLOAD_ORDER:
        lines.append(f"\n### {workload.upper()}")
        subset = read_summary[read_summary["workload"] == workload]
        for size in SIZE_ORDER:
            size_subset = subset[subset["size_label"] == size]
            if len(size_subset) >= 2:
                baseline = size_subset[size_subset["implementation"] == "Baseline (VM)"]
                ml = size_subset[size_subset["implementation"] == "ML (Red Neuronal)"]
                if not baseline.empty and not ml.empty:
                    bl_bw = baseline.iloc[0]["bw_MB_s_mean"]
                    ml_bw = ml.iloc[0]["bw_MB_s_mean"]
                    bw_delta = ((ml_bw - bl_bw) / bl_bw * 100) if bl_bw else 0
                    winner_short = "ML ✓" if bw_delta > 0 else "Baseline ✓"
                    lines.append(f"- **{size}**: {bl_bw:.1f} → {ml_bw:.1f} MB/s ({bw_delta:+.1f}%) [{winner_short}]")

    lines.extend([
        "",
        "## Observaciones",
        "- Gráfico `comparativa_metricas.png` muestra comparación lado a lado",
        "- CSV `comparativa_metricas.csv` contiene datos agregados detallados",
    ])

    output_dir.joinpath("reporte_comparativa.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    print("\n" + "="*70)
    print("ANÁLISIS INTEGRAL: BASELINE VM vs ML".center(70))
    print("="*70)

    # Procesar baseline
    df_baseline, summary_baseline = process_baseline()

    # Procesar ML
    df_ml, summary_ml = process_ml()

    # Análisis comparativo
    process_comparative(df_baseline, df_ml)

    print("\n" + "="*70)
    print("✓ ANÁLISIS COMPLETADO EXITOSAMENTE".center(70))
    print("="*70)
    print(f"\nResultados en: {OUTPUT_BASE}")
    print("  ├── baseline/")
    print("  ├── ml/")
    print("  └── comparativa/")
    print()


if __name__ == "__main__":
    main()
