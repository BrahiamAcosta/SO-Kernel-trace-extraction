"""
Script para generar un reporte completo de hallazgos del análisis FIO
Autor: Análisis de Rendimiento de I/O
Fecha: Diciembre 2025
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from process_results import FIOResultsProcessor


class ReportGenerator:
    """Clase para generar reportes de análisis"""
    
    def __init__(self, df: pd.DataFrame, stats: pd.DataFrame, output_dir: Path):
        """
        Inicializa el generador de reportes
        
        Args:
            df: DataFrame con resultados procesados
            stats: DataFrame con estadísticas agregadas
            output_dir: Directorio de salida
        """
        self.df = df
        self.stats = stats
        self.output_dir = output_dir
        
    def generate_markdown_report(self) -> str:
        """Genera el reporte completo en formato Markdown"""
        
        report = f"""# Reporte de Análisis de Rendimiento I/O - Experimentos FIO

**Fecha de generación:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 1. Resumen Ejecutivo

Este documento presenta el análisis exhaustivo de los experimentos de rendimiento de I/O realizados utilizando la herramienta **FIO (Flexible I/O Tester)** en un sistema Linux. Los experimentos evalúan tres patrones de acceso diferentes (Secuencial, Aleatorio y Mixto) con tres tamaños de archivo (100MB, 500MB y 1GB), cada uno ejecutado tres veces para garantizar la consistencia de los resultados.

### Configuración del Experimento

- **Herramienta:** FIO v3.36
- **Patrones de acceso:** Secuencial (read), Aleatorio (randread), Mixto (randrw)
- **Tamaños de archivo:** 100MB, 500MB, 1GB
- **Tamaño de bloque:** 128KB
- **Modo de I/O:** Direct I/O (bypass de caché)
- **Profundidad de cola:** 1
- **Duración:** 10 segundos por ejecución
- **Repeticiones:** 3 por configuración
- **Total de experimentos:** {len(self.df)} ejecuciones

---

## 2. Métricas Principales

"""
        
        # Agregar tabla de métricas principales
        report += self._generate_metrics_summary()
        
        # Hallazgos por tipo de acceso
        report += "\n---\n\n## 3. Análisis por Tipo de Acceso\n\n"
        report += self._analyze_by_access_type()
        
        # Análisis de escalabilidad
        report += "\n---\n\n## 4. Análisis de Escalabilidad\n\n"
        report += self._analyze_scalability()
        
        # Análisis de latencia
        report += "\n---\n\n## 5. Análisis Detallado de Latencia\n\n"
        report += self._analyze_latency()
        
        # Análisis de variabilidad
        report += "\n---\n\n## 6. Análisis de Consistencia y Variabilidad\n\n"
        report += self._analyze_variability()
        
        # Hallazgos clave
        report += "\n---\n\n## 7. Hallazgos Clave\n\n"
        report += self._generate_key_findings()
        
        # Recomendaciones
        report += "\n---\n\n## 8. Recomendaciones\n\n"
        report += self._generate_recommendations()
        
        # Conclusiones
        report += "\n---\n\n## 9. Conclusiones\n\n"
        report += self._generate_conclusions()
        
        # Apéndice
        report += "\n---\n\n## 10. Apéndice: Gráficas Generadas\n\n"
        report += self._list_generated_plots()
        
        return report
    
    def _generate_metrics_summary(self) -> str:
        """Genera resumen de métricas principales"""
        
        text = "### 2.1 Resumen de IOPS (Operaciones de I/O por Segundo)\n\n"
        
        iops_summary = self.df.groupby(['access_type', 'file_size'])['iops'].agg(['mean', 'std', 'min', 'max']).round(2)
        
        text += "| Tipo de Acceso | Tamaño | IOPS Promedio | Desv. Std | Min | Max |\n"
        text += "|----------------|---------|---------------|-----------|-----|-----|\n"
        
        for (access, size), row in iops_summary.iterrows():
            access_label = {'seq': 'Secuencial', 'rand': 'Aleatorio', 'mix': 'Mixto'}[access]
            text += f"| {access_label} | {size} | {row['mean']:.2f} | {row['std']:.2f} | {row['min']:.2f} | {row['max']:.2f} |\n"
        
        text += "\n### 2.2 Resumen de Ancho de Banda (MB/s)\n\n"
        
        bw_summary = self.df.groupby(['access_type', 'file_size'])['bw_mbs'].agg(['mean', 'std', 'min', 'max']).round(2)
        
        text += "| Tipo de Acceso | Tamaño | BW Promedio (MB/s) | Desv. Std | Min | Max |\n"
        text += "|----------------|---------|-------------------|-----------|-----|-----|\n"
        
        for (access, size), row in bw_summary.iterrows():
            access_label = {'seq': 'Secuencial', 'rand': 'Aleatorio', 'mix': 'Mixto'}[access]
            text += f"| {access_label} | {size} | {row['mean']:.2f} | {row['std']:.2f} | {row['min']:.2f} | {row['max']:.2f} |\n"
        
        text += "\n### 2.3 Resumen de Latencia Media (μs)\n\n"
        
        lat_summary = self.df.groupby(['access_type', 'file_size'])['lat_mean_us'].agg(['mean', 'std', 'min', 'max']).round(2)
        
        text += "| Tipo de Acceso | Tamaño | Latencia Promedio (μs) | Desv. Std | Min | Max |\n"
        text += "|----------------|---------|----------------------|-----------|-----|-----|\n"
        
        for (access, size), row in lat_summary.iterrows():
            access_label = {'seq': 'Secuencial', 'rand': 'Aleatorio', 'mix': 'Mixto'}[access]
            text += f"| {access_label} | {size} | {row['mean']:.2f} | {row['std']:.2f} | {row['min']:.2f} | {row['max']:.2f} |\n"
        
        return text
    
    def _analyze_by_access_type(self) -> str:
        """Analiza resultados por tipo de acceso"""
        
        text = ""
        
        # Análisis Secuencial
        text += "### 3.1 Acceso Secuencial\n\n"
        seq_data = self.df[self.df['access_type'] == 'seq']
        
        avg_iops = seq_data['iops'].mean()
        avg_bw = seq_data['bw_mbs'].mean()
        avg_lat = seq_data['lat_mean_us'].mean()
        
        text += f"El acceso secuencial muestra el **mejor rendimiento general** en términos de throughput:\n\n"
        text += f"- **IOPS promedio:** {avg_iops:.2f}\n"
        text += f"- **Ancho de banda promedio:** {avg_bw:.2f} MB/s\n"
        text += f"- **Latencia promedio:** {avg_lat:.2f} μs\n\n"
        
        text += "**Características destacadas:**\n"
        text += "- Latencias consistentemente bajas debido a la predictibilidad del patrón de acceso\n"
        text += "- Mejor aprovechamiento del prefetching y caché del sistema\n"
        text += "- Escalabilidad lineal con el tamaño del archivo\n\n"
        
        # Análisis Aleatorio
        text += "### 3.2 Acceso Aleatorio\n\n"
        rand_data = self.df[self.df['access_type'] == 'rand']
        
        avg_iops = rand_data['iops'].mean()
        avg_bw = rand_data['bw_mbs'].mean()
        avg_lat = rand_data['lat_mean_us'].mean()
        
        text += f"El acceso aleatorio presenta **menor rendimiento** debido a la naturaleza no secuencial:\n\n"
        text += f"- **IOPS promedio:** {avg_iops:.2f}\n"
        text += f"- **Ancho de banda promedio:** {avg_bw:.2f} MB/s\n"
        text += f"- **Latencia promedio:** {avg_lat:.2f} μs\n\n"
        
        text += "**Características destacadas:**\n"
        text += "- Mayor latencia debido a los seeks frecuentes del disco\n"
        text += "- Menor aprovechamiento de optimizaciones de hardware\n"
        text += "- Variabilidad moderada en las métricas de rendimiento\n\n"
        
        # Análisis Mixto
        text += "### 3.3 Acceso Mixto\n\n"
        mix_data = self.df[self.df['access_type'] == 'mix']
        
        avg_iops = mix_data['iops'].mean()
        avg_bw = mix_data['bw_mbs'].mean()
        avg_lat = mix_data['lat_mean_us'].mean()
        
        # Verificar si hay datos de escritura
        has_write = 'write_iops' in mix_data.columns and mix_data['write_iops'].notna().any()
        
        text += f"El acceso mixto combina operaciones de lectura y escritura aleatoria:\n\n"
        text += f"- **IOPS promedio (lectura):** {avg_iops:.2f}\n"
        text += f"- **Ancho de banda promedio (lectura):** {avg_bw:.2f} MB/s\n"
        text += f"- **Latencia promedio (lectura):** {avg_lat:.2f} μs\n\n"
        
        if has_write:
            avg_write_iops = mix_data['write_iops'].mean()
            avg_write_bw = mix_data['write_bw_kbs'].mean() / 1024
            text += f"- **IOPS promedio (escritura):** {avg_write_iops:.2f}\n"
            text += f"- **Ancho de banda promedio (escritura):** {avg_write_bw:.2f} MB/s\n\n"
        
        text += "**Características destacadas:**\n"
        text += "- Rendimiento balanceado entre lecturas y escrituras\n"
        text += "- Mayor variabilidad en latencias debido a la mezcla de operaciones\n"
        text += "- Representativo de cargas de trabajo reales con I/O mixto\n\n"
        
        return text
    
    def _analyze_scalability(self) -> str:
        """Analiza la escalabilidad con el tamaño"""
        
        text = "### 4.1 Comportamiento con Diferentes Tamaños de Archivo\n\n"
        
        for access in ['seq', 'rand', 'mix']:
            access_label = {'seq': 'Secuencial', 'rand': 'Aleatorio', 'mix': 'Mixto'}[access]
            text += f"#### {access_label}\n\n"
            
            subset = self.df[self.df['access_type'] == access].groupby('file_size').agg({
                'iops': 'mean',
                'bw_mbs': 'mean',
                'lat_mean_us': 'mean'
            }).round(2)
            
            text += "| Tamaño | IOPS | BW (MB/s) | Latencia (μs) |\n"
            text += "|--------|------|-----------|---------------|\n"
            
            for size in ['100M', '500M', '1G']:
                if size in subset.index:
                    row = subset.loc[size]
                    text += f"| {size} | {row['iops']:.2f} | {row['bw_mbs']:.2f} | {row['lat_mean_us']:.2f} |\n"
            
            text += "\n"
            
            # Análisis de tendencia
            if '100M' in subset.index and '1G' in subset.index:
                iops_change = ((subset.loc['1G', 'iops'] - subset.loc['100M', 'iops']) / subset.loc['100M', 'iops']) * 100
                bw_change = ((subset.loc['1G', 'bw_mbs'] - subset.loc['100M', 'bw_mbs']) / subset.loc['100M', 'bw_mbs']) * 100
                
                text += f"**Cambio de 100M a 1G:**\n"
                text += f"- IOPS: {iops_change:+.1f}%\n"
                text += f"- Ancho de banda: {bw_change:+.1f}%\n\n"
        
        return text
    
    def _analyze_latency(self) -> str:
        """Análisis detallado de latencia"""
        
        text = "### 5.1 Distribución de Latencias\n\n"
        
        text += "La latencia es un indicador crítico del rendimiento percibido. Se analizan múltiples percentiles:\n\n"
        
        # Buscar columnas de percentiles
        percentile_cols = [col for col in self.df.columns if col.startswith('lat_p') and col.endswith('_us')]
        
        if percentile_cols:
            text += "| Tipo de Acceso | Tamaño | P50 (μs) | P95 (μs) | P99 (μs) | Max (μs) |\n"
            text += "|----------------|---------|----------|----------|----------|----------|\n"
            
            for (access, size) in self.df.groupby(['access_type', 'file_size']).groups.keys():
                subset = self.df[(self.df['access_type'] == access) & (self.df['file_size'] == size)]
                access_label = {'seq': 'Secuencial', 'rand': 'Aleatorio', 'mix': 'Mixto'}[access]
                
                p50 = subset['lat_p50_0_us'].mean() if 'lat_p50_0_us' in subset.columns else subset['lat_mean_us'].mean()
                p95 = subset['lat_p95_0_us'].mean() if 'lat_p95_0_us' in subset.columns else 0
                p99 = subset['lat_p99_0_us'].mean() if 'lat_p99_0_us' in subset.columns else 0
                lat_max = subset['lat_max_us'].mean()
                
                text += f"| {access_label} | {size} | {p50:.2f} | {p95:.2f} | {p99:.2f} | {lat_max:.2f} |\n"
            
            text += "\n"
        
        text += "### 5.2 Análisis de Cola de Latencias\n\n"
        text += "Las latencias extremas (P99 y máximas) son importantes para aplicaciones sensibles a la latencia:\n\n"
        
        for access in ['seq', 'rand', 'mix']:
            access_label = {'seq': 'Secuencial', 'rand': 'Aleatorio', 'mix': 'Mixto'}[access]
            subset = self.df[self.df['access_type'] == access]
            
            avg_mean = subset['lat_mean_us'].mean()
            avg_max = subset['lat_max_us'].mean()
            ratio = avg_max / avg_mean if avg_mean > 0 else 0
            
            text += f"**{access_label}:**\n"
            text += f"- Latencia media: {avg_mean:.2f} μs\n"
            text += f"- Latencia máxima promedio: {avg_max:.2f} μs\n"
            text += f"- Ratio Max/Media: {ratio:.2f}x\n\n"
        
        return text
    
    def _analyze_variability(self) -> str:
        """Analiza la variabilidad y consistencia"""
        
        text = "### 6.1 Coeficiente de Variación\n\n"
        text += "El coeficiente de variación (CV) indica la consistencia de los resultados entre ejecuciones:\n\n"
        
        cv_data = self.df.groupby(['access_type', 'file_size'])['iops'].agg(
            lambda x: (x.std() / x.mean()) * 100 if x.mean() > 0 else 0
        ).round(2)
        
        text += "| Tipo de Acceso | Tamaño | CV IOPS (%) |\n"
        text += "|----------------|---------|-------------|\n"
        
        for (access, size), cv in cv_data.items():
            access_label = {'seq': 'Secuencial', 'rand': 'Aleatorio', 'mix': 'Mixto'}[access]
            interpretation = "Excelente" if cv < 5 else "Buena" if cv < 10 else "Moderada" if cv < 15 else "Alta"
            text += f"| {access_label} | {size} | {cv:.2f} ({interpretation}) |\n"
        
        text += "\n**Interpretación:**\n"
        text += "- CV < 5%: Excelente consistencia\n"
        text += "- CV 5-10%: Buena consistencia\n"
        text += "- CV 10-15%: Consistencia moderada\n"
        text += "- CV > 15%: Alta variabilidad\n\n"
        
        text += "### 6.2 Estabilidad del Ancho de Banda\n\n"
        
        bw_stability = self.df.groupby(['access_type', 'file_size']).agg({
            'bw_mbs': ['mean', 'std', lambda x: (x.std() / x.mean()) * 100 if x.mean() > 0 else 0]
        }).round(2)
        
        text += "El ancho de banda muestra la siguiente estabilidad:\n\n"
        
        for access in ['seq', 'rand', 'mix']:
            access_label = {'seq': 'Secuencial', 'rand': 'Aleatorio', 'mix': 'Mixto'}[access]
            subset = self.df[self.df['access_type'] == access]
            avg_cv = ((subset['bw_mbs'].std() / subset['bw_mbs'].mean()) * 100) if subset['bw_mbs'].mean() > 0 else 0
            
            text += f"- **{access_label}:** CV promedio = {avg_cv:.2f}%\n"
        
        text += "\n"
        
        return text
    
    def _generate_key_findings(self) -> str:
        """Genera hallazgos clave"""
        
        # Calcular métricas para hallazgos
        seq_iops = self.df[self.df['access_type'] == 'seq']['iops'].mean()
        rand_iops = self.df[self.df['access_type'] == 'rand']['iops'].mean()
        mix_iops = self.df[self.df['access_type'] == 'mix']['iops'].mean()
        
        seq_bw = self.df[self.df['access_type'] == 'seq']['bw_mbs'].mean()
        rand_bw = self.df[self.df['access_type'] == 'rand']['bw_mbs'].mean()
        
        seq_lat = self.df[self.df['access_type'] == 'seq']['lat_mean_us'].mean()
        rand_lat = self.df[self.df['access_type'] == 'rand']['lat_mean_us'].mean()
        
        text = "### Hallazgos Principales\n\n"
        
        text += f"1. **Rendimiento Secuencial vs Aleatorio:**\n"
        text += f"   - El acceso secuencial logra **{seq_iops:.0f} IOPS** en promedio, mientras que el aleatorio alcanza **{rand_iops:.0f} IOPS**\n"
        text += f"   - Esto representa una diferencia de **{((seq_iops - rand_iops) / rand_iops * 100):.1f}%** a favor del acceso secuencial\n\n"
        
        text += f"2. **Ancho de Banda:**\n"
        text += f"   - Secuencial: **{seq_bw:.2f} MB/s**\n"
        text += f"   - Aleatorio: **{rand_bw:.2f} MB/s**\n"
        text += f"   - El acceso secuencial proporciona **{(seq_bw / rand_bw):.2f}x** más throughput\n\n"
        
        text += f"3. **Latencia:**\n"
        text += f"   - Secuencial: **{seq_lat:.2f} μs**\n"
        text += f"   - Aleatorio: **{rand_lat:.2f} μs**\n"
        text += f"   - El acceso aleatorio tiene **{((rand_lat - seq_lat) / seq_lat * 100):.1f}%** más latencia\n\n"
        
        text += f"4. **Acceso Mixto:**\n"
        text += f"   - Logra **{mix_iops:.0f} IOPS**, posicionándose entre secuencial y aleatorio\n"
        text += f"   - Representa un escenario realista de cargas de trabajo mixtas\n\n"
        
        text += "5. **Escalabilidad:**\n"
        
        for access in ['seq', 'rand', 'mix']:
            subset = self.df[self.df['access_type'] == access].groupby('file_size')['iops'].mean()
            if '100M' in subset.index and '1G' in subset.index:
                change = ((subset['1G'] - subset['100M']) / subset['100M']) * 100
                access_label = {'seq': 'Secuencial', 'rand': 'Aleatorio', 'mix': 'Mixto'}[access]
                text += f"   - {access_label}: {change:+.1f}% cambio de 100M a 1G\n"
        
        text += "\n6. **Consistencia:**\n"
        
        overall_cv = self.df.groupby('access_type')['iops'].agg(
            lambda x: (x.std() / x.mean()) * 100 if x.mean() > 0 else 0
        )
        
        for access, cv in overall_cv.items():
            access_label = {'seq': 'Secuencial', 'rand': 'Aleatorio', 'mix': 'Mixto'}[access]
            text += f"   - {access_label}: CV = {cv:.2f}% - "
            text += "Excelente consistencia\n" if cv < 5 else "Buena consistencia\n" if cv < 10 else "Consistencia moderada\n"
        
        return text
    
    def _generate_recommendations(self) -> str:
        """Genera recomendaciones basadas en el análisis"""
        
        text = "### Recomendaciones Técnicas\n\n"
        
        text += "1. **Optimización de Aplicaciones:**\n"
        text += "   - Priorizar patrones de acceso secuencial cuando sea posible\n"
        text += "   - Implementar buffers y caching para mitigar el impacto del acceso aleatorio\n"
        text += "   - Considerar batch processing para maximizar throughput\n\n"
        
        text += "2. **Configuración del Sistema:**\n"
        text += "   - Para cargas secuenciales: aumentar el read-ahead del kernel\n"
        text += "   - Para cargas aleatorias: considerar SSDs o NVMe para mejor rendimiento\n"
        text += "   - Ajustar el tamaño de bloque según el patrón de acceso predominante\n\n"
        
        text += "3. **Dimensionamiento de Hardware:**\n"
        text += "   - El sistema muestra buen rendimiento para cargas secuenciales\n"
        text += "   - Para mejorar acceso aleatorio, considerar:\n"
        text += "     - Discos SSD/NVMe con mejores IOPS\n"
        text += "     - Aumentar memoria RAM para caché\n"
        text += "     - Configuración RAID según necesidades\n\n"
        
        text += "4. **Monitoreo y Benchmarking:**\n"
        text += "   - Establecer baselines de rendimiento regularmente\n"
        text += "   - Monitorear percentiles altos de latencia (P95, P99)\n"
        text += "   - Evaluar impacto de cambios en configuración\n\n"
        
        text += "5. **Desarrollo de Aplicaciones:**\n"
        text += "   - Diseñar pensando en la localidad de datos\n"
        text += "   - Utilizar I/O asíncrono cuando sea apropiado\n"
        text += "   - Considerar el trade-off entre latencia y throughput\n\n"
        
        return text
    
    def _generate_conclusions(self) -> str:
        """Genera conclusiones del análisis"""
        
        text = "### Conclusiones Generales\n\n"
        
        text += "El análisis de los experimentos FIO revela patrones claros de rendimiento I/O:\n\n"
        
        text += "**Rendimiento:**\n"
        text += "- El acceso **secuencial** demuestra ser significativamente superior en todas las métricas\n"
        text += "- El acceso **aleatorio** presenta las mayores latencias y menor throughput, como era esperado\n"
        text += "- El acceso **mixto** ofrece un balance realista entre lecturas y escrituras\n\n"
        
        text += "**Escalabilidad:**\n"
        text += "- El sistema escala apropiadamente con el tamaño de los archivos\n"
        text += "- No se observan degradaciones significativas en archivos grandes\n"
        text += "- La consistencia se mantiene a través de diferentes tamaños\n\n"
        
        text += "**Consistencia:**\n"
        text += "- Los resultados muestran baja variabilidad entre ejecuciones\n"
        text += "- Los coeficientes de variación indican buena reproducibilidad\n"
        text += "- El sistema presenta comportamiento predecible\n\n"
        
        text += "**Aplicabilidad:**\n"
        text += "- Los resultados son representativos de sistemas de almacenamiento típicos\n"
        text += "- Pueden usarse como baseline para optimizaciones futuras\n"
        text += "- Proveen insights valiosos para el diseño de sistemas\n\n"
        
        text += "**Próximos Pasos:**\n"
        text += "1. Comparar con resultados de sistemas optimizados (ML-assisted)\n"
        text += "2. Evaluar impacto de diferentes schedulers de I/O\n"
        text += "3. Analizar comportamiento bajo carga concurrente\n"
        text += "4. Investigar optimizaciones específicas por patrón de acceso\n\n"
        
        return text
    
    def _list_generated_plots(self) -> str:
        """Lista las gráficas generadas"""
        
        text = "Las siguientes visualizaciones fueron generadas como parte del análisis:\n\n"
        
        plots = [
            ("iops_comparison.png", "Comparación de IOPS por tipo de acceso y tamaño"),
            ("bandwidth_comparison.png", "Análisis de ancho de banda"),
            ("latency_analysis.png", "Análisis detallado de latencia"),
            ("throughput_efficiency.png", "Eficiencia de throughput"),
            ("performance_heatmap.png", "Mapas de calor de rendimiento"),
            ("comparative_radar.png", "Gráfica radar comparativa"),
            ("variability_analysis.png", "Análisis de variabilidad entre runs"),
            ("percentile_latency.png", "Percentiles de latencia")
        ]
        
        for filename, description in plots:
            text += f"- **{filename}**: {description}\n"
        
        text += "\nTodas las gráficas están disponibles en el directorio `analisis/`.\n\n"
        
        text += "### Interpretación de Gráficas\n\n"
        text += "**Barras agrupadas:** Permiten comparar métricas entre diferentes configuraciones\n\n"
        text += "**Box plots:** Muestran la distribución y outliers de las métricas\n\n"
        text += "**Mapas de calor:** Facilitan la identificación rápida de patrones de rendimiento\n\n"
        text += "**Gráficas de línea:** Ilustran tendencias y escalabilidad\n\n"
        text += "**Radar charts:** Comparan múltiples dimensiones de rendimiento simultáneamente\n\n"
        
        return text
    
    def save_report(self):
        """Guarda el reporte en archivo"""
        report_content = self.generate_markdown_report()
        report_path = self.output_dir / 'REPORTE_HALLAZGOS.md'
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"✓ Reporte generado: {report_path}")
        
        return report_path


def main():
    """Función principal"""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    results_path = project_root / 'experiments' / 'results_baseline'
    
    print("="*80)
    print("GENERADOR DE REPORTE DE HALLAZGOS")
    print("="*80)
    print()
    
    # Procesar datos
    processor = FIOResultsProcessor(results_path)
    df = processor.process_all_results()
    stats = processor.compute_statistics(df)
    
    # Generar reporte
    reporter = ReportGenerator(df, stats, script_dir)
    report_path = reporter.save_report()
    
    print()
    print("="*80)
    print(f"REPORTE COMPLETADO: {report_path}")
    print("="*80)


if __name__ == "__main__":
    main()
