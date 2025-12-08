"""
Script para procesar y analizar los resultados de los experimentos FIO
Autor: Análisis de Rendimiento de I/O
Fecha: Diciembre 2025
"""

import json
import os
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple

class FIOResultsProcessor:
    """Clase para procesar los resultados de experimentos FIO"""
    
    def __init__(self, base_path: str):
        """
        Inicializa el procesador de resultados
        
        Args:
            base_path: Ruta base donde se encuentran los resultados
        """
        self.base_path = Path(base_path)
        self.access_types = ['seq', 'rand', 'mix']
        self.file_sizes = ['100M', '500M', '1G']
        self.runs = 3
        self.results_data = []
        
    def load_single_result(self, file_path: Path) -> Dict:
        """
        Carga un archivo JSON individual de resultados FIO
        
        Args:
            file_path: Ruta al archivo JSON
            
        Returns:
            Diccionario con los datos procesados del archivo
        """
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            job = data['jobs'][0]
            
            # Extraer métricas de lectura
            read_metrics = {
                'io_bytes': job['read']['io_bytes'],
                'io_kbytes': job['read']['io_kbytes'],
                'bw_bytes': job['read']['bw_bytes'],
                'bw_kbs': job['read']['bw'],
                'iops': job['read']['iops'],
                'runtime_ms': job['read']['runtime'],
                'total_ios': job['read']['total_ios'],
                'lat_mean_ns': job['read']['lat_ns']['mean'],
                'lat_min_ns': job['read']['lat_ns']['min'],
                'lat_max_ns': job['read']['lat_ns']['max'],
                'lat_stddev_ns': job['read']['lat_ns']['stddev'],
                'clat_mean_ns': job['read']['clat_ns']['mean'],
                'clat_stddev_ns': job['read']['clat_ns']['stddev'],
                'bw_min': job['read']['bw_min'],
                'bw_max': job['read']['bw_max'],
                'bw_mean': job['read']['bw_mean'],
                'bw_dev': job['read']['bw_dev'],
                'iops_mean': job['read']['iops_mean'],
                'iops_stddev': job['read']['iops_stddev']
            }
            
            # Extraer percentiles de latencia
            percentiles = {}
            for p, val in job['read']['clat_ns']['percentile'].items():
                p_str = f"p{float(p):.1f}".replace('.', '_')
                percentiles[f'lat_{p_str}_ns'] = val
            
            read_metrics.update(percentiles)
            
            # Extraer métricas de escritura si existen (para modo mix)
            write_metrics = {}
            if job['write']['io_bytes'] > 0:
                write_metrics = {
                    'write_io_bytes': job['write']['io_bytes'],
                    'write_io_kbytes': job['write']['io_kbytes'],
                    'write_bw_bytes': job['write']['bw_bytes'],
                    'write_bw_kbs': job['write']['bw'],
                    'write_iops': job['write']['iops'],
                    'write_runtime_ms': job['write']['runtime'],
                    'write_total_ios': job['write']['total_ios'],
                    'write_lat_mean_ns': job['write']['lat_ns']['mean'],
                    'write_lat_min_ns': job['write']['lat_ns']['min'],
                    'write_lat_max_ns': job['write']['lat_ns']['max'],
                    'write_lat_stddev_ns': job['write']['lat_ns']['stddev']
                }
            
            result = {**read_metrics, **write_metrics}
            return result
            
        except Exception as e:
            print(f"Error al cargar {file_path}: {e}")
            return None
    
    def process_all_results(self) -> pd.DataFrame:
        """
        Procesa todos los archivos de resultados y crea un DataFrame
        
        Returns:
            DataFrame con todos los resultados procesados
        """
        all_data = []
        
        for access_type in self.access_types:
            for file_size in self.file_sizes:
                for run in range(1, self.runs + 1):
                    file_path = self.base_path / access_type / file_size / f"result_{file_size}_run{run}.json"
                    
                    if file_path.exists():
                        result = self.load_single_result(file_path)
                        
                        if result:
                            result['access_type'] = access_type
                            result['file_size'] = file_size
                            result['run'] = run
                            all_data.append(result)
                    else:
                        print(f"Advertencia: No se encontró {file_path}")
        
        df = pd.DataFrame(all_data)
        
        # Convertir latencias de nanosegundos a microsegundos para mejor legibilidad
        latency_cols = [col for col in df.columns if 'lat' in col.lower() and '_ns' in col]
        for col in latency_cols:
            new_col = col.replace('_ns', '_us')
            df[new_col] = df[col] / 1000
        
        # Convertir runtime a segundos
        if 'runtime_ms' in df.columns:
            df['runtime_s'] = df['runtime_ms'] / 1000
        
        # Convertir bytes a MB/GB
        if 'io_bytes' in df.columns:
            df['io_mb'] = df['io_bytes'] / (1024 * 1024)
            df['io_gb'] = df['io_bytes'] / (1024 * 1024 * 1024)
        
        if 'bw_bytes' in df.columns:
            df['bw_mbs'] = df['bw_bytes'] / (1024 * 1024)
        
        return df
    
    def compute_statistics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula estadísticas agregadas por tipo de acceso y tamaño de archivo
        
        Args:
            df: DataFrame con los resultados procesados
            
        Returns:
            DataFrame con estadísticas agregadas
        """
        # Métricas principales para agregar
        metrics = [
            'iops', 'bw_mbs', 'lat_mean_us', 'lat_stddev_us',
            'clat_mean_us', 'clat_stddev_us', 'io_mb', 
            'bw_mean', 'iops_mean', 'throughput_effective'
        ]
        
        # Calcular throughput efectivo (MB procesados / tiempo real)
        df['throughput_effective'] = df['io_mb'] / df['runtime_s']
        
        # Filtrar solo las métricas que existen en el DataFrame
        available_metrics = [m for m in metrics if m in df.columns]
        
        # Agrupar por tipo de acceso y tamaño de archivo
        stats = df.groupby(['access_type', 'file_size'])[available_metrics].agg([
            'mean', 'std', 'min', 'max', 'median'
        ]).round(2)
        
        return stats
    
    def save_processed_data(self, df: pd.DataFrame, output_path: str):
        """
        Guarda los datos procesados en CSV
        
        Args:
            df: DataFrame con los datos procesados
            output_path: Ruta donde guardar el CSV
        """
        df.to_csv(output_path, index=False)
        print(f"Datos procesados guardados en: {output_path}")
    
    def save_statistics(self, stats: pd.DataFrame, output_path: str):
        """
        Guarda las estadísticas agregadas en CSV
        
        Args:
            stats: DataFrame con las estadísticas
            output_path: Ruta donde guardar el CSV
        """
        stats.to_csv(output_path)
        print(f"Estadísticas guardadas en: {output_path}")


def main():
    """Función principal para ejecutar el procesamiento"""
    
    # Configuración de rutas
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    results_path = project_root / 'experiments' / 'results_baseline'
    output_dir = script_dir
    
    # Crear directorio de salida si no existe
    output_dir.mkdir(exist_ok=True, parents=True)
    
    print("="*80)
    print("PROCESADOR DE RESULTADOS FIO - ANÁLISIS DE RENDIMIENTO DE I/O")
    print("="*80)
    print()
    
    # Inicializar procesador
    processor = FIOResultsProcessor(results_path)
    
    # Procesar todos los resultados
    print("Procesando archivos de resultados...")
    df = processor.process_all_results()
    
    print(f"\nTotal de experimentos procesados: {len(df)}")
    print(f"Tipos de acceso: {df['access_type'].unique()}")
    print(f"Tamaños de archivo: {df['file_size'].unique()}")
    print(f"Número de runs: {df['run'].nunique()}")
    print()
    
    # Guardar datos procesados
    processed_file = output_dir / 'processed_results.csv'
    processor.save_processed_data(df, processed_file)
    
    # Calcular estadísticas
    print("Calculando estadísticas agregadas...")
    stats = processor.compute_statistics(df)
    
    # Guardar estadísticas
    stats_file = output_dir / 'statistics_summary.csv'
    processor.save_statistics(stats, stats_file)
    
    # Mostrar resumen de estadísticas
    print("\n" + "="*80)
    print("RESUMEN DE ESTADÍSTICAS")
    print("="*80)
    print("\nIOPS Promedio por configuración:")
    print(stats['iops']['mean'].unstack())
    print("\nAncho de banda promedio (MB/s) por configuración:")
    print(stats['bw_mbs']['mean'].unstack())
    print("\nLatencia media (μs) por configuración:")
    print(stats['lat_mean_us']['mean'].unstack())
    print()
    
    print("="*80)
    print("PROCESAMIENTO COMPLETADO")
    print("="*80)
    
    return df, stats


if __name__ == "__main__":
    df, stats = main()
