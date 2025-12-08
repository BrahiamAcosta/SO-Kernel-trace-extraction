"""
Script para generar visualizaciones de los resultados de los experimentos FIO
Autor: Análisis de Rendimiento de I/O
Fecha: Diciembre 2025
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from process_results import FIOResultsProcessor

# Configuración de estilo
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 10
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['xtick.labelsize'] = 10
plt.rcParams['ytick.labelsize'] = 10
plt.rcParams['legend.fontsize'] = 10


class FIOPlotter:
    """Clase para generar gráficas de los resultados FIO"""
    
    def __init__(self, df: pd.DataFrame, output_dir: Path):
        """
        Inicializa el generador de gráficas
        
        Args:
            df: DataFrame con los resultados procesados
            output_dir: Directorio donde guardar las gráficas
        """
        self.df = df
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True, parents=True)
        
        # Mapeo de nombres para mejor visualización
        self.access_labels = {
            'seq': 'Secuencial',
            'rand': 'Aleatorio',
            'mix': 'Mixto'
        }
        
        self.size_labels = {
            '100M': '100 MB',
            '500M': '500 MB',
            '1G': '1 GB'
        }
    
    def plot_iops_comparison(self):
        """Gráfica de comparación de IOPS por tipo de acceso y tamaño"""
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        
        # Gráfica 1: Barras agrupadas
        pivot_data = self.df.groupby(['access_type', 'file_size'])['iops'].mean().unstack()
        pivot_data.index = pivot_data.index.map(self.access_labels)
        pivot_data.columns = [self.size_labels[col] for col in pivot_data.columns]
        
        pivot_data.plot(kind='bar', ax=axes[0], width=0.8, edgecolor='black', linewidth=1.2)
        axes[0].set_title('IOPS Promedio por Tipo de Acceso y Tamaño de Archivo', 
                          fontsize=14, fontweight='bold')
        axes[0].set_xlabel('Tipo de Acceso', fontsize=12)
        axes[0].set_ylabel('IOPS', fontsize=12)
        axes[0].legend(title='Tamaño de Archivo', loc='upper right')
        axes[0].grid(axis='y', alpha=0.3)
        axes[0].set_xticklabels(axes[0].get_xticklabels(), rotation=0)
        
        # Gráfica 2: Box plot para ver variabilidad
        sns.boxplot(data=self.df, x='access_type', y='iops', hue='file_size', ax=axes[1])
        axes[1].set_title('Distribución de IOPS por Configuración', 
                          fontsize=14, fontweight='bold')
        axes[1].set_xlabel('Tipo de Acceso', fontsize=12)
        axes[1].set_ylabel('IOPS', fontsize=12)
        axes[1].legend(title='Tamaño', labels=['100 MB', '500 MB', '1 GB'])
        
        # Reemplazar labels del eje x
        axes[1].set_xticklabels([self.access_labels[t.get_text()] for t in axes[1].get_xticklabels()])
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'iops_comparison.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ Gráfica generada: iops_comparison.png")
    
    def plot_bandwidth_comparison(self):
        """Gráfica de comparación de ancho de banda"""
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        
        # Gráfica 1: Barras agrupadas
        pivot_data = self.df.groupby(['access_type', 'file_size'])['bw_mbs'].mean().unstack()
        pivot_data.index = pivot_data.index.map(self.access_labels)
        pivot_data.columns = [self.size_labels[col] for col in pivot_data.columns]
        
        pivot_data.plot(kind='bar', ax=axes[0], width=0.8, edgecolor='black', linewidth=1.2, color=['#3498db', '#e74c3c', '#2ecc71'])
        axes[0].set_title('Ancho de Banda Promedio (MB/s) por Tipo de Acceso y Tamaño', 
                          fontsize=14, fontweight='bold')
        axes[0].set_xlabel('Tipo de Acceso', fontsize=12)
        axes[0].set_ylabel('Ancho de Banda (MB/s)', fontsize=12)
        axes[0].legend(title='Tamaño de Archivo', loc='upper right')
        axes[0].grid(axis='y', alpha=0.3)
        axes[0].set_xticklabels(axes[0].get_xticklabels(), rotation=0)
        
        # Gráfica 2: Líneas para ver tendencias
        for access in self.df['access_type'].unique():
            subset = self.df[self.df['access_type'] == access].groupby('file_size')['bw_mbs'].mean()
            axes[1].plot([self.size_labels[s] for s in subset.index], 
                        subset.values, 
                        marker='o', 
                        linewidth=2, 
                        markersize=8,
                        label=self.access_labels[access])
        
        axes[1].set_title('Tendencia del Ancho de Banda por Tamaño de Archivo', 
                          fontsize=14, fontweight='bold')
        axes[1].set_xlabel('Tamaño de Archivo', fontsize=12)
        axes[1].set_ylabel('Ancho de Banda (MB/s)', fontsize=12)
        axes[1].legend(title='Tipo de Acceso')
        axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'bandwidth_comparison.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ Gráfica generada: bandwidth_comparison.png")
    
    def plot_latency_analysis(self):
        """Gráficas de análisis de latencia"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        
        # Gráfica 1: Latencia media por configuración
        pivot_data = self.df.groupby(['access_type', 'file_size'])['lat_mean_us'].mean().unstack()
        pivot_data.index = pivot_data.index.map(self.access_labels)
        pivot_data.columns = [self.size_labels[col] for col in pivot_data.columns]
        
        pivot_data.plot(kind='bar', ax=axes[0, 0], width=0.8, edgecolor='black', linewidth=1.2)
        axes[0, 0].set_title('Latencia Media (μs) por Tipo de Acceso y Tamaño', 
                             fontsize=14, fontweight='bold')
        axes[0, 0].set_xlabel('Tipo de Acceso', fontsize=12)
        axes[0, 0].set_ylabel('Latencia (μs)', fontsize=12)
        axes[0, 0].legend(title='Tamaño de Archivo')
        axes[0, 0].grid(axis='y', alpha=0.3)
        axes[0, 0].set_xticklabels(axes[0, 0].get_xticklabels(), rotation=0)
        
        # Gráfica 2: Desviación estándar de latencia
        pivot_std = self.df.groupby(['access_type', 'file_size'])['lat_stddev_us'].mean().unstack()
        pivot_std.index = pivot_std.index.map(self.access_labels)
        pivot_std.columns = [self.size_labels[col] for col in pivot_std.columns]
        
        pivot_std.plot(kind='bar', ax=axes[0, 1], width=0.8, edgecolor='black', linewidth=1.2, color=['#e67e22', '#9b59b6', '#1abc9c'])
        axes[0, 1].set_title('Variabilidad de Latencia (Desv. Estándar en μs)', 
                             fontsize=14, fontweight='bold')
        axes[0, 1].set_xlabel('Tipo de Acceso', fontsize=12)
        axes[0, 1].set_ylabel('Desviación Estándar (μs)', fontsize=12)
        axes[0, 1].legend(title='Tamaño de Archivo')
        axes[0, 1].grid(axis='y', alpha=0.3)
        axes[0, 1].set_xticklabels(axes[0, 1].get_xticklabels(), rotation=0)
        
        # Gráfica 3: Violin plot para distribución de latencias
        sns.violinplot(data=self.df, x='access_type', y='lat_mean_us', hue='file_size', 
                      ax=axes[1, 0], split=False)
        axes[1, 0].set_title('Distribución de Latencia por Configuración', 
                             fontsize=14, fontweight='bold')
        axes[1, 0].set_xlabel('Tipo de Acceso', fontsize=12)
        axes[1, 0].set_ylabel('Latencia Media (μs)', fontsize=12)
        axes[1, 0].legend(title='Tamaño', labels=['100 MB', '500 MB', '1 GB'])
        axes[1, 0].set_xticklabels([self.access_labels[t.get_text()] for t in axes[1, 0].get_xticklabels()])
        
        # Gráfica 4: Comparación latencia min vs max
        for access in self.df['access_type'].unique():
            subset = self.df[self.df['access_type'] == access].groupby('file_size').agg({
                'lat_min_us': 'mean',
                'lat_max_us': 'mean'
            })
            x_pos = np.arange(len(subset))
            width = 0.25
            offset = {'seq': -width, 'rand': 0, 'mix': width}[access]
            
            axes[1, 1].bar(x_pos + offset, subset['lat_max_us'], width, 
                          label=f'{self.access_labels[access]} (Max)', alpha=0.7)
            axes[1, 1].bar(x_pos + offset, subset['lat_min_us'], width, 
                          label=f'{self.access_labels[access]} (Min)', alpha=0.9)
        
        axes[1, 1].set_title('Rango de Latencias (Min vs Max) por Configuración', 
                             fontsize=14, fontweight='bold')
        axes[1, 1].set_xlabel('Tamaño de Archivo', fontsize=12)
        axes[1, 1].set_ylabel('Latencia (μs)', fontsize=12)
        axes[1, 1].set_xticks(range(len(self.df['file_size'].unique())))
        axes[1, 1].set_xticklabels([self.size_labels[s] for s in sorted(self.df['file_size'].unique())])
        axes[1, 1].legend(loc='upper left', fontsize=8)
        axes[1, 1].grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'latency_analysis.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ Gráfica generada: latency_analysis.png")
    
    def plot_throughput_efficiency(self):
        """Gráfica de eficiencia de throughput"""
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        
        # Calcular throughput efectivo si no existe
        if 'throughput_effective' not in self.df.columns:
            self.df['throughput_effective'] = self.df['io_mb'] / self.df['runtime_s']
        
        # Gráfica 1: Throughput efectivo
        pivot_data = self.df.groupby(['access_type', 'file_size'])['throughput_effective'].mean().unstack()
        pivot_data.index = pivot_data.index.map(self.access_labels)
        pivot_data.columns = [self.size_labels[col] for col in pivot_data.columns]
        
        pivot_data.plot(kind='bar', ax=axes[0], width=0.8, edgecolor='black', linewidth=1.2, color=['#16a085', '#c0392b', '#f39c12'])
        axes[0].set_title('Throughput Efectivo (MB/s) por Configuración', 
                          fontsize=14, fontweight='bold')
        axes[0].set_xlabel('Tipo de Acceso', fontsize=12)
        axes[0].set_ylabel('Throughput (MB/s)', fontsize=12)
        axes[0].legend(title='Tamaño de Archivo', loc='upper right')
        axes[0].grid(axis='y', alpha=0.3)
        axes[0].set_xticklabels(axes[0].get_xticklabels(), rotation=0)
        
        # Gráfica 2: Total de datos procesados
        pivot_io = self.df.groupby(['access_type', 'file_size'])['io_gb'].mean().unstack()
        pivot_io.index = pivot_io.index.map(self.access_labels)
        pivot_io.columns = [self.size_labels[col] for col in pivot_io.columns]
        
        pivot_io.plot(kind='bar', ax=axes[1], width=0.8, edgecolor='black', linewidth=1.2, color=['#8e44ad', '#27ae60', '#e74c3c'])
        axes[1].set_title('Total de Datos Procesados (GB) en 10 segundos', 
                          fontsize=14, fontweight='bold')
        axes[1].set_xlabel('Tipo de Acceso', fontsize=12)
        axes[1].set_ylabel('Datos Procesados (GB)', fontsize=12)
        axes[1].legend(title='Tamaño de Archivo', loc='upper right')
        axes[1].grid(axis='y', alpha=0.3)
        axes[1].set_xticklabels(axes[1].get_xticklabels(), rotation=0)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'throughput_efficiency.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ Gráfica generada: throughput_efficiency.png")
    
    def plot_performance_heatmap(self):
        """Mapa de calor del rendimiento general"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        
        metrics = [
            ('iops', 'IOPS'),
            ('bw_mbs', 'Ancho de Banda (MB/s)'),
            ('lat_mean_us', 'Latencia Media (μs)'),
            ('throughput_effective', 'Throughput Efectivo (MB/s)')
        ]
        
        for idx, (metric, title) in enumerate(metrics):
            ax = axes[idx // 2, idx % 2]
            
            if metric in self.df.columns:
                pivot_data = self.df.groupby(['access_type', 'file_size'])[metric].mean().unstack()
                pivot_data.index = pivot_data.index.map(self.access_labels)
                pivot_data.columns = [self.size_labels[col] for col in pivot_data.columns]
                
                # Usar colormap invertido para latencia (menos es mejor)
                cmap = 'YlOrRd_r' if 'lat' in metric else 'YlGnBu'
                
                sns.heatmap(pivot_data, annot=True, fmt='.1f', cmap=cmap, 
                           ax=ax, linewidths=1, linecolor='white', cbar_kws={'label': title})
                ax.set_title(f'Mapa de Calor: {title}', fontsize=14, fontweight='bold')
                ax.set_xlabel('Tamaño de Archivo', fontsize=12)
                ax.set_ylabel('Tipo de Acceso', fontsize=12)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'performance_heatmap.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ Gráfica generada: performance_heatmap.png")
    
    def plot_comparative_radar(self):
        """Gráfica radar comparativa de rendimiento normalizado"""
        from math import pi
        
        # Métricas para el radar (normalizadas)
        metrics_to_plot = ['iops', 'bw_mbs', 'throughput_effective']
        
        # Agregar datos por tipo de acceso
        radar_data = {}
        for access in self.df['access_type'].unique():
            subset = self.df[self.df['access_type'] == access][metrics_to_plot].mean()
            # Normalizar a escala 0-100
            normalized = (subset - self.df[metrics_to_plot].min()) / (self.df[metrics_to_plot].max() - self.df[metrics_to_plot].min()) * 100
            radar_data[access] = normalized
        
        # Crear gráfica radar
        categories = ['IOPS', 'Ancho de Banda', 'Throughput']
        N = len(categories)
        
        angles = [n / float(N) * 2 * pi for n in range(N)]
        angles += angles[:1]
        
        fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))
        
        colors = {'seq': '#3498db', 'rand': '#e74c3c', 'mix': '#2ecc71'}
        
        for access, values in radar_data.items():
            values_list = values.tolist()
            values_list += values_list[:1]
            ax.plot(angles, values_list, 'o-', linewidth=2, 
                   label=self.access_labels[access], color=colors[access])
            ax.fill(angles, values_list, alpha=0.15, color=colors[access])
        
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, size=12)
        ax.set_ylim(0, 100)
        ax.set_ylabel('Rendimiento Normalizado (%)', size=12)
        ax.grid(True)
        ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
        ax.set_title('Comparación de Rendimiento Normalizado por Tipo de Acceso', 
                    size=14, fontweight='bold', pad=20)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'comparative_radar.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ Gráfica generada: comparative_radar.png")
    
    def plot_variability_analysis(self):
        """Análisis de variabilidad entre runs"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        
        # Gráfica 1: Variabilidad de IOPS entre runs
        for access in self.df['access_type'].unique():
            subset = self.df[self.df['access_type'] == access].groupby(['file_size', 'run'])['iops'].mean().unstack()
            subset.index = [self.size_labels[s] for s in subset.index]
            subset.plot(ax=axes[0, 0], marker='o', linewidth=2, label=self.access_labels[access])
        
        axes[0, 0].set_title('Variabilidad de IOPS entre Ejecuciones', 
                             fontsize=14, fontweight='bold')
        axes[0, 0].set_xlabel('Tamaño de Archivo', fontsize=12)
        axes[0, 0].set_ylabel('IOPS', fontsize=12)
        axes[0, 0].legend(title='Tipo de Acceso')
        axes[0, 0].grid(True, alpha=0.3)
        
        # Gráfica 2: Coeficiente de variación
        cv_data = self.df.groupby(['access_type', 'file_size'])['iops'].agg(
            lambda x: (x.std() / x.mean()) * 100
        ).unstack()
        cv_data.index = cv_data.index.map(self.access_labels)
        cv_data.columns = [self.size_labels[col] for col in cv_data.columns]
        
        cv_data.plot(kind='bar', ax=axes[0, 1], width=0.8, edgecolor='black', linewidth=1.2)
        axes[0, 1].set_title('Coeficiente de Variación de IOPS (%)', 
                             fontsize=14, fontweight='bold')
        axes[0, 1].set_xlabel('Tipo de Acceso', fontsize=12)
        axes[0, 1].set_ylabel('CV (%)', fontsize=12)
        axes[0, 1].legend(title='Tamaño de Archivo')
        axes[0, 1].grid(axis='y', alpha=0.3)
        axes[0, 1].set_xticklabels(axes[0, 1].get_xticklabels(), rotation=0)
        axes[0, 1].axhline(y=5, color='r', linestyle='--', linewidth=1, label='5% threshold')
        
        # Gráfica 3: Variabilidad de latencia
        for access in self.df['access_type'].unique():
            subset = self.df[self.df['access_type'] == access].groupby(['file_size', 'run'])['lat_mean_us'].mean().unstack()
            subset.index = [self.size_labels[s] for s in subset.index]
            subset.plot(ax=axes[1, 0], marker='s', linewidth=2, label=self.access_labels[access])
        
        axes[1, 0].set_title('Variabilidad de Latencia entre Ejecuciones', 
                             fontsize=14, fontweight='bold')
        axes[1, 0].set_xlabel('Tamaño de Archivo', fontsize=12)
        axes[1, 0].set_ylabel('Latencia Media (μs)', fontsize=12)
        axes[1, 0].legend(title='Tipo de Acceso')
        axes[1, 0].grid(True, alpha=0.3)
        
        # Gráfica 4: Estabilidad del ancho de banda
        stability = self.df.groupby(['access_type', 'file_size']).agg({
            'bw_mbs': ['mean', 'std']
        })
        stability.columns = ['mean', 'std']
        stability_pivot = stability['mean'].unstack()
        stability_pivot.index = stability_pivot.index.map(self.access_labels)
        stability_pivot.columns = [self.size_labels[col] for col in stability_pivot.columns]
        
        stability_std = stability['std'].unstack()
        stability_std.index = stability_std.index.map(self.access_labels)
        stability_std.columns = [self.size_labels[col] for col in stability_std.columns]
        
        x = np.arange(len(stability_pivot.index))
        width = 0.25
        
        for i, col in enumerate(stability_pivot.columns):
            axes[1, 1].bar(x + i*width, stability_pivot[col], width, 
                          yerr=stability_std[col], label=col, 
                          capsize=5, edgecolor='black', linewidth=1.2)
        
        axes[1, 1].set_title('Ancho de Banda: Media ± Desv. Estándar', 
                             fontsize=14, fontweight='bold')
        axes[1, 1].set_xlabel('Tipo de Acceso', fontsize=12)
        axes[1, 1].set_ylabel('Ancho de Banda (MB/s)', fontsize=12)
        axes[1, 1].set_xticks(x + width)
        axes[1, 1].set_xticklabels(stability_pivot.index)
        axes[1, 1].legend(title='Tamaño de Archivo')
        axes[1, 1].grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'variability_analysis.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ Gráfica generada: variability_analysis.png")
    
    def plot_percentile_latency(self):
        """Gráfica de percentiles de latencia"""
        fig, axes = plt.subplots(1, 3, figsize=(18, 6))
        
        percentiles = ['lat_p50_0_us', 'lat_p95_0_us', 'lat_p99_0_us']
        percentile_names = ['P50 (Mediana)', 'P95', 'P99']
        
        for idx, (perc_col, perc_name) in enumerate(zip(percentiles, percentile_names)):
            if perc_col in self.df.columns:
                pivot_data = self.df.groupby(['access_type', 'file_size'])[perc_col].mean().unstack()
                pivot_data.index = pivot_data.index.map(self.access_labels)
                pivot_data.columns = [self.size_labels[col] for col in pivot_data.columns]
                
                pivot_data.plot(kind='bar', ax=axes[idx], width=0.8, 
                               edgecolor='black', linewidth=1.2)
                axes[idx].set_title(f'Latencia {perc_name} (μs)', 
                                   fontsize=14, fontweight='bold')
                axes[idx].set_xlabel('Tipo de Acceso', fontsize=12)
                axes[idx].set_ylabel('Latencia (μs)', fontsize=12)
                axes[idx].legend(title='Tamaño de Archivo')
                axes[idx].grid(axis='y', alpha=0.3)
                axes[idx].set_xticklabels(axes[idx].get_xticklabels(), rotation=0)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'percentile_latency.png', dpi=300, bbox_inches='tight')
        plt.close()
        print("✓ Gráfica generada: percentile_latency.png")
    
    def generate_all_plots(self):
        """Genera todas las gráficas"""
        print("\n" + "="*80)
        print("GENERANDO VISUALIZACIONES")
        print("="*80)
        print()
        
        self.plot_iops_comparison()
        self.plot_bandwidth_comparison()
        self.plot_latency_analysis()
        self.plot_throughput_efficiency()
        self.plot_performance_heatmap()
        self.plot_comparative_radar()
        self.plot_variability_analysis()
        self.plot_percentile_latency()
        
        print()
        print("="*80)
        print(f"TODAS LAS GRÁFICAS GENERADAS EN: {self.output_dir}")
        print("="*80)


def main():
    """Función principal"""
    # Configuración de rutas
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    results_path = project_root / 'experiments' / 'results_baseline'
    output_dir = script_dir
    
    print("="*80)
    print("GENERADOR DE VISUALIZACIONES - ANÁLISIS DE RENDIMIENTO FIO")
    print("="*80)
    
    # Procesar datos
    processor = FIOResultsProcessor(results_path)
    df = processor.process_all_results()
    
    # Generar gráficas
    plotter = FIOPlotter(df, output_dir)
    plotter.generate_all_plots()


if __name__ == "__main__":
    main()
