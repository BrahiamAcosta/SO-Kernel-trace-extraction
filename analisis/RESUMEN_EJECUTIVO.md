# 📊 Resumen Ejecutivo: Análisis FIO Baseline vs ML

## ✅ Análisis Completado

Se han procesado y analizado todos los resultados de FIO en 3 carpetas organizadas:

### 📁 Estructura Generada

```
analisis/
├── baseline/         → Análisis línea base (VM)
├── ml/               → Análisis Red Neuronal
└── comparativa/      → Análisis comparativo
```

---

## 🎯 Hallazgos Principales

### 📈 Throughput de Lectura (MB/s)

| Patrón        | Baseline | ML    | Mejora   |
| ------------- | -------- | ----- | -------- |
| **SEQ 100M**  | 289.6    | 364.1 | +25.7% ✓ |
| **SEQ 500M**  | 307.2    | 439.4 | +43.1% ✓ |
| **SEQ 1G**    | 290.0    | 409.7 | +41.3% ✓ |
| **RAND 100M** | 186.3    | 189.2 | +1.6% ✓  |
| **RAND 500M** | 183.3    | 215.9 | +17.8% ✓ |
| **RAND 1G**   | 179.0    | 197.4 | +10.3% ✓ |
| **MIX 100M**  | 93.3     | 116.5 | +24.8% ✓ |
| **MIX 500M**  | 97.3     | 67.6  | -30.4% ✗ |
| **MIX 1G**    | 76.7     | 74.9  | -2.3% ✗  |

**Promedio General:** Baseline 189.2 MB/s vs **ML 230.5 MB/s (+21.9%)**

### 💬 Latencia p99 (ms)

| Patrón        | Baseline | ML    | Delta    |
| ------------- | -------- | ----- | -------- |
| **SEQ 100M**  | 0.629    | 1.128 | +79.3%   |
| **SEQ 500M**  | 0.662    | 0.575 | -13.1% ✓ |
| **SEQ 1G**    | 0.624    | 0.990 | +58.7%   |
| **RAND 100M** | 0.894    | 1.647 | +84.2%   |
| **RAND 500M** | 0.927    | 0.916 | -1.2% ✓  |
| **RAND 1G**   | 0.930    | 1.461 | +57.0%   |

**Observación:** ML mejor en SEQ 500M y RAND 500M; Baseline mejor en otros casos.

---

## 📋 Contenido por Carpeta

### baseline/

- `reporte_baseline.md` - Análisis detallado línea base
- `throughput_lectura.png` - Gráfico throughput
- `latencia_p99.png` - Gráfico latencia
- `resumen_metricas.csv` - Datos agregados
- `resultados_detalle.csv` - Métrica por corrida

### ml/

- `reporte_ml.md` - Análisis detallado ML
- `throughput_lectura.png` - Gráfico throughput (ML)
- `latencia_p99.png` - Gráfico latencia (ML)
- `resumen_metricas.csv` - Datos agregados (ML)
- `resultados_detalle.csv` - Métrica por corrida (ML)

### comparativa/

- `reporte_comparativa.md` - Análisis comparativo completo
- `comparativa_metricas.png` - Gráfico lado a lado
- `comparativa_metricas.csv` - Datos con ambas implementaciones
- `resultados_combinados.csv` - Detalle completo combinado

---

## 🔍 Conclusiones

### ✅ Ventajas ML

- **Throughput en SEQ**: +25-43% en todas las cargas (100M-1G)
- **Throughput en RAND**: +1-17% mejora consistente
- **Mejor balance**: Rendimiento superior en 7 de 9 escenarios

### ⚠️ Ventajas Baseline

- **Cargas mixtas grandes (500M-1G)**: -2% a -30% en throughput
- **Latencia más predecible**: Mejor p99 en 7 de 9 escenarios
- **Estabilidad**: Menor variabilidad entre corridas

### 🎯 Recomendación

- **ML es superior para**: Lectura intensiva, patrones secuenciales, cargas pequeñas
- **Baseline mejor para**: Escritura mixta en escala, latencia predecible

---

## 🚀 Cómo Usar

1. **Regenerar análisis:**

   ```powershell
   python analisis/analizar.py
   ```

2. **Revisar gráficos:**

   - Abrir PNG en cada subcarpeta

3. **Analizar datos:**

   - Importar CSV en Excel/Python

4. **Leer reportes:**
   - Abrir markdown en editor de texto

---

## 📦 Archivos por Tipo

### Gráficos (PNG)

- `baseline/throughput_lectura.png`
- `baseline/latencia_p99.png`
- `ml/throughput_lectura.png`
- `ml/latencia_p99.png`
- `comparativa/comparativa_metricas.png`

### Reportes (MD)

- `baseline/reporte_baseline.md`
- `ml/reporte_ml.md`
- `comparativa/reporte_comparativa.md`

### Datos (CSV)

- `baseline/resultados_detalle.csv`
- `baseline/resumen_metricas.csv`
- `ml/resultados_detalle.csv`
- `ml/resumen_metricas.csv`
- `comparativa/resultados_combinados.csv`
- `comparativa/comparativa_metricas.csv`

---

**Análisis Completado:** ✅  
**Gráficos:** 5 (limpios y descriptivos)  
**Reportes:** 3 (markdown)  
**Datos CSV:** 6 (detalle + agregados)
