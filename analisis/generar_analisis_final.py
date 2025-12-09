"""Genera gráficas comparativas y análisis detallado de resultados
Baseline vs ML con justificaciones técnicas.
"""
from __future__ import annotations

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
BASELINE_METRICS = BASE_DIR / "analisis" / "baseline" / "resumen_metricas.csv"
ML_METRICS = BASE_DIR / "analisis" / "ml" / "resumen_metricas.csv"
OUTPUT_DIR = BASE_DIR / "analisis"

sns.set_theme(style="whitegrid", palette="Set2")
plt.rcParams['figure.dpi'] = 150
plt.rcParams['font.size'] = 10


def load_data():
    """Carga datos de baseline y ML."""
    baseline = pd.read_csv(BASELINE_METRICS)
    baseline['implementation'] = 'Baseline'
    
    ml = pd.read_csv(ML_METRICS)
    ml['implementation'] = 'ML'
    
    combined = pd.concat([baseline, ml], ignore_index=True)
    return combined


def plot_throughput_comparison(df: pd.DataFrame, output_dir: Path):
    """Gráfica comparativa de throughput por patrón."""
    read_data = df[df['op'] == 'read'].copy()
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
    
    workloads = ['seq', 'rand', 'mix']
    titles = ['Secuencial', 'Aleatorio', 'Mixto']
    
    for idx, (workload, title) in enumerate(zip(workloads, titles)):
        ax = axes[idx]
        data = read_data[read_data['workload'] == workload]
        
        sns.barplot(
            data=data,
            x='size_label',
            y='bw_MB_s_mean',
            hue='implementation',
            ax=ax,
            errorbar='sd',
            alpha=0.85
        )
        
        ax.set_title(f'{title}', fontsize=12, fontweight='bold')
        ax.set_xlabel('Tamaño de Prueba', fontsize=10)
        if idx == 0:
            ax.set_ylabel('Throughput (MB/s)', fontsize=10)
        else:
            ax.set_ylabel('')
        
        if idx < 2:
            ax.get_legend().remove()
        else:
            ax.legend(title='Implementación', loc='upper right', fontsize=9)
    
    plt.suptitle('Comparación de Throughput de Lectura: Baseline vs ML', 
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(output_dir / 'analisis_throughput_comparativo.png', dpi=150, bbox_inches='tight')
    plt.close()


def plot_latency_comparison(df: pd.DataFrame, output_dir: Path):
    """Gráfica comparativa de latencia p99."""
    read_data = df[df['op'] == 'read'].copy()
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=False)
    
    workloads = ['seq', 'rand', 'mix']
    titles = ['Secuencial', 'Aleatorio', 'Mixto']
    
    for idx, (workload, title) in enumerate(zip(workloads, titles)):
        ax = axes[idx]
        data = read_data[read_data['workload'] == workload]
        
        sns.barplot(
            data=data,
            x='size_label',
            y='p99_ms_mean',
            hue='implementation',
            ax=ax,
            alpha=0.85
        )
        
        ax.set_title(f'{title}', fontsize=12, fontweight='bold')
        ax.set_xlabel('Tamaño de Prueba', fontsize=10)
        if idx == 0:
            ax.set_ylabel('Latencia p99 (ms)', fontsize=10)
        else:
            ax.set_ylabel('')
        
        if idx < 2:
            ax.get_legend().remove()
        else:
            ax.legend(title='Implementación', loc='upper right', fontsize=9)
    
    plt.suptitle('Comparación de Latencia p99 de Lectura: Baseline vs ML', 
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(output_dir / 'analisis_latencia_comparativo.png', dpi=150, bbox_inches='tight')
    plt.close()


def plot_mixed_latency_detail(df: pd.DataFrame, output_dir: Path):
    """Gráfica detallada de latencia en patrón mixto (read + write)."""
    mix_data = df[df['workload'] == 'mix'].copy()
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    
    # Lectura
    ax = axes[0]
    read_data = mix_data[mix_data['op'] == 'read']
    sns.barplot(
        data=read_data,
        x='size_label',
        y='p99_ms_mean',
        hue='implementation',
        ax=ax,
        alpha=0.85
    )
    ax.set_title('Latencia p99 - Lectura en Mixto', fontsize=12, fontweight='bold')
    ax.set_xlabel('Tamaño de Prueba', fontsize=10)
    ax.set_ylabel('Latencia p99 (ms)', fontsize=10)
    ax.legend(title='Implementación', fontsize=9)
    ax.set_yscale('log')
    
    # Escritura
    ax = axes[1]
    write_data = mix_data[mix_data['op'] == 'write']
    sns.barplot(
        data=write_data,
        x='size_label',
        y='p99_ms_mean',
        hue='implementation',
        ax=ax,
        alpha=0.85
    )
    ax.set_title('Latencia p99 - Escritura en Mixto', fontsize=12, fontweight='bold')
    ax.set_xlabel('Tamaño de Prueba', fontsize=10)
    ax.set_ylabel('Latencia p99 (ms)', fontsize=10)
    ax.legend(title='Implementación', fontsize=9)
    ax.set_yscale('log')
    
    plt.suptitle('Análisis Detallado de Latencia en Patrón Mixto', 
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(output_dir / 'analisis_mixto_latencia_detalle.png', dpi=150, bbox_inches='tight')
    plt.close()


def plot_improvement_heatmap(df: pd.DataFrame, output_dir: Path):
    """Heatmap de mejoras porcentuales ML vs Baseline."""
    read_data = df[df['op'] == 'read'].copy()
    
    # Calcular mejoras
    baseline = read_data[read_data['implementation'] == 'Baseline'].set_index(['workload', 'size_label'])
    ml = read_data[read_data['implementation'] == 'ML'].set_index(['workload', 'size_label'])
    
    improvement = ((ml['bw_MB_s_mean'] - baseline['bw_MB_s_mean']) / baseline['bw_MB_s_mean'] * 100).reset_index()
    improvement_pivot = improvement.pivot(index='workload', columns='size_label', values='bw_MB_s_mean')
    improvement_pivot = improvement_pivot.reindex(['seq', 'rand', 'mix'])
    improvement_pivot = improvement_pivot[['100M', '500M', '1G']]
    
    fig, ax = plt.subplots(figsize=(8, 4))
    sns.heatmap(
        improvement_pivot,
        annot=True,
        fmt='.1f',
        cmap='RdYlGn',
        center=0,
        cbar_kws={'label': 'Mejora (%)'},
        linewidths=0.5,
        ax=ax
    )
    ax.set_title('Mejora de Throughput: ML vs Baseline (%)', fontsize=13, fontweight='bold')
    ax.set_xlabel('Tamaño de Prueba', fontsize=11)
    ax.set_ylabel('Patrón de Acceso', fontsize=11)
    ax.set_yticklabels(['Secuencial', 'Aleatorio', 'Mixto'], rotation=0)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'analisis_mejoras_heatmap.png', dpi=150, bbox_inches='tight')
    plt.close()


def plot_latency_improvement_heatmap(df: pd.DataFrame, output_dir: Path):
    """Heatmap de cambios en latencia ML vs Baseline."""
    read_data = df[df['op'] == 'read'].copy()
    
    # Calcular cambios en latencia (valores negativos = mejora)
    baseline = read_data[read_data['implementation'] == 'Baseline'].set_index(['workload', 'size_label'])
    ml = read_data[read_data['implementation'] == 'ML'].set_index(['workload', 'size_label'])
    
    latency_change = ((ml['p99_ms_mean'] - baseline['p99_ms_mean']) / baseline['p99_ms_mean'] * 100).reset_index()
    latency_pivot = latency_change.pivot(index='workload', columns='size_label', values='p99_ms_mean')
    latency_pivot = latency_pivot.reindex(['seq', 'rand', 'mix'])
    latency_pivot = latency_pivot[['100M', '500M', '1G']]
    
    fig, ax = plt.subplots(figsize=(8, 4))
    
    # Usar escala divergente: rojo = peor (aumento latencia), verde = mejor (reducción latencia)
    sns.heatmap(
        latency_pivot,
        annot=True,
        fmt='.1f',
        cmap='RdYlGn_r',  # Invertido: rojo = malo, verde = bueno
        center=0,
        cbar_kws={'label': 'Cambio en Latencia (%)'},
        linewidths=0.5,
        ax=ax,
        vmin=-20,  # Ajuste para mejor visualización
        vmax=100   # Limitar escala para ver patrones (mix 500M está fuera de escala)
    )
    ax.set_title('Cambio en Latencia p99: ML vs Baseline (%)', fontsize=13, fontweight='bold')
    ax.set_xlabel('Tamaño de Prueba', fontsize=11)
    ax.set_ylabel('Patrón de Acceso', fontsize=11)
    ax.set_yticklabels(['Secuencial', 'Aleatorio', 'Mixto'], rotation=0)
    
    # Añadir nota sobre mix 500M
    ax.text(1.5, 2.5, '⚠ mix 500M: +6089%\n(fuera de escala)', 
            ha='center', va='center', fontsize=8, 
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    plt.savefig(output_dir / 'analisis_latencia_heatmap.png', dpi=150, bbox_inches='tight')
    plt.close()


def plot_variability_comparison(df: pd.DataFrame, output_dir: Path):
    """Compara variabilidad (desviación estándar) entre implementaciones."""
    read_data = df[df['op'] == 'read'].copy()
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    sns.barplot(
        data=read_data,
        x='workload',
        y='bw_MB_s_std',
        hue='implementation',
        ax=ax,
        alpha=0.85
    )
    
    ax.set_title('Variabilidad de Throughput (Desviación Estándar)', 
                 fontsize=13, fontweight='bold')
    ax.set_xlabel('Patrón de Acceso', fontsize=11)
    ax.set_ylabel('Desviación Estándar (MB/s)', fontsize=11)
    ax.set_xticklabels(['Secuencial', 'Aleatorio', 'Mixto'])
    ax.legend(title='Implementación', fontsize=10)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'analisis_variabilidad.png', dpi=150, bbox_inches='tight')
    plt.close()


def generate_statistics_table(df: pd.DataFrame, output_dir: Path):
    """Genera tabla de estadísticas clave."""
    read_data = df[df['op'] == 'read'].copy()
    
    stats = []
    for impl in ['Baseline', 'ML']:
        impl_data = read_data[read_data['implementation'] == impl]
        stats.append({
            'Implementación': impl,
            'Throughput Promedio (MB/s)': impl_data['bw_MB_s_mean'].mean(),
            'Throughput Máximo (MB/s)': impl_data['bw_MB_s_mean'].max(),
            'Latencia p99 Promedio (ms)': impl_data['p99_ms_mean'].mean(),
            'Latencia p99 Mínima (ms)': impl_data['p99_ms_mean'].min(),
            'Desv. Estándar Promedio': impl_data['bw_MB_s_std'].mean(),
        })
    
    stats_df = pd.DataFrame(stats)
    stats_df.to_csv(output_dir / 'estadisticas_generales.csv', index=False)
    return stats_df


def main():
    print("\n" + "="*70)
    print("ANÁLISIS COMPARATIVO FINAL: Baseline vs ML".center(70))
    print("="*70 + "\n")
    
    # Cargar datos
    print("📊 Cargando datos...")
    df = load_data()
    
    # Generar gráficas
    print("📈 Generando gráficas comparativas...")
    
    print("  ├─ Throughput comparativo...")
    plot_throughput_comparison(df, OUTPUT_DIR)
    
    print("  ├─ Latencia comparativa...")
    plot_latency_comparison(df, OUTPUT_DIR)
    
    print("  ├─ Detalle latencia mixto...")
    plot_mixed_latency_detail(df, OUTPUT_DIR)
    
    print("  ├─ Heatmap de mejoras...")
    plot_improvement_heatmap(df, OUTPUT_DIR)
    
    print("  ├─ Heatmap de latencia...")
    plot_latency_improvement_heatmap(df, OUTPUT_DIR)
    
    print("  ├─ Análisis de variabilidad...")
    plot_variability_comparison(df, OUTPUT_DIR)
    
    # Estadísticas
    print("\n📋 Generando estadísticas generales...")
    stats = generate_statistics_table(df, OUTPUT_DIR)
    print(stats.to_string(index=False))
    
    print("\n" + "="*70)
    print("✅ ANÁLISIS COMPLETADO".center(70))
    print("="*70)
    print(f"\nGráficas generadas en: {OUTPUT_DIR}")
    print("  ├─ analisis_throughput_comparativo.png")
    print("  ├─ analisis_latencia_comparativo.png")
    print("  ├─ analisis_mixto_latencia_detalle.png")
    print("  ├─ analisis_mejoras_heatmap.png")
    print("  ├─ analisis_latencia_heatmap.png")
    print("  ├─ analisis_variabilidad.png")
    print("  └─ estadisticas_generales.csv")
    print()


if __name__ == "__main__":
    main()
