"""
Script principal para ejecutar el análisis completo de resultados FIO
Autor: Análisis de Rendimiento de I/O
Fecha: Diciembre 2025

Este script ejecuta todo el pipeline de análisis:
1. Procesamiento de resultados
2. Generación de gráficas
3. Generación de reporte de hallazgos
"""

from pathlib import Path
import sys

# Importar módulos de análisis
from process_results import FIOResultsProcessor
from generate_plots import FIOPlotter
from generate_report import ReportGenerator


def print_header(title):
    """Imprime un encabezado formateado"""
    print("\n" + "="*80)
    print(title.center(80))
    print("="*80 + "\n")


def main():
    """Función principal del pipeline de análisis"""
    
    print_header("ANÁLISIS COMPLETO DE RESULTADOS FIO")
    print("Este script ejecutará el pipeline completo de análisis:")
    print("  1. Procesamiento de datos")
    print("  2. Generación de gráficas")
    print("  3. Generación de reporte")
    print()
    
    # Configuración de rutas
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    results_path = project_root / 'experiments' / 'results_baseline'
    output_dir = script_dir
    
    # Verificar que exista el directorio de resultados
    if not results_path.exists():
        print(f"❌ ERROR: No se encuentra el directorio de resultados: {results_path}")
        print("   Por favor, verifica que los resultados estén en la ubicación correcta.")
        sys.exit(1)
    
    try:
        # ===========================
        # FASE 1: PROCESAMIENTO
        # ===========================
        print_header("FASE 1: PROCESAMIENTO DE DATOS")
        
        processor = FIOResultsProcessor(results_path)
        df = processor.process_all_results()
        
        print(f"✓ Total de experimentos procesados: {len(df)}")
        print(f"✓ Tipos de acceso: {', '.join(df['access_type'].unique())}")
        print(f"✓ Tamaños de archivo: {', '.join(df['file_size'].unique())}")
        print(f"✓ Número de runs: {df['run'].nunique()}")
        
        # Guardar datos procesados
        processed_file = output_dir / 'processed_results.csv'
        processor.save_processed_data(df, processed_file)
        
        # Calcular y guardar estadísticas
        stats = processor.compute_statistics(df)
        stats_file = output_dir / 'statistics_summary.csv'
        processor.save_statistics(stats, stats_file)
        
        print("\n✓ Archivos CSV generados:")
        print(f"  - {processed_file.name}")
        print(f"  - {stats_file.name}")
        
        # ===========================
        # FASE 2: VISUALIZACIÓN
        # ===========================
        print_header("FASE 2: GENERACIÓN DE GRÁFICAS")
        
        plotter = FIOPlotter(df, output_dir)
        plotter.generate_all_plots()
        
        # ===========================
        # FASE 3: REPORTE
        # ===========================
        print_header("FASE 3: GENERACIÓN DE REPORTE")
        
        reporter = ReportGenerator(df, stats, output_dir)
        report_path = reporter.save_report()
        
        print(f"\n✓ Reporte de hallazgos generado: {report_path.name}")
        
        # ===========================
        # RESUMEN FINAL
        # ===========================
        print_header("ANÁLISIS COMPLETADO EXITOSAMENTE")
        
        print("📁 Archivos generados en el directorio 'analisis/':\n")
        
        print("📊 Datos procesados:")
        print("  ├─ processed_results.csv")
        print("  └─ statistics_summary.csv")
        
        print("\n📈 Gráficas:")
        print("  ├─ iops_comparison.png")
        print("  ├─ bandwidth_comparison.png")
        print("  ├─ latency_analysis.png")
        print("  ├─ throughput_efficiency.png")
        print("  ├─ performance_heatmap.png")
        print("  ├─ comparative_radar.png")
        print("  ├─ variability_analysis.png")
        print("  └─ percentile_latency.png")
        
        print("\n📄 Documentación:")
        print("  ├─ REPORTE_HALLAZGOS.md")
        print("  └─ README.md")
        
        print("\n" + "="*80)
        print("Para ver el reporte completo, abre: REPORTE_HALLAZGOS.md")
        print("="*80)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ ERROR durante el análisis: {e}")
        print(f"   Tipo de error: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
