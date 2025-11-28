"""
Script para construir el dataset desde el CSV consolidado.

Este script lee consolidated_dataset.csv que ya tiene características calculadas
y las mapea a las 5 características que espera el modelo de red neuronal.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


def map_label_to_int(label: str) -> int:
    """Mapea etiquetas de texto a enteros."""
    label_lower = label.lower().strip()
    if label_lower == "sequential":
        return 0
    elif label_lower == "random":
        return 1
    elif label_lower == "mixed":
        return 2
    else:
        raise ValueError(f"Etiqueta desconocida: {label}")


def extract_features_from_consolidated(df: pd.DataFrame) -> np.ndarray:
    """
    Extrae las 5 características que espera el modelo desde el CSV consolidado.
    
    Mapeo:
    1. trace_avg_sector_distance → distancia promedio (feature 1)
    2. Calculamos std desde trace_sector_jump_ratio y otras métricas → variabilidad (feature 2)
    3. trace_avg_request_size_kb * 1024 → tamaño promedio I/O en bytes (feature 3)
    4. 1 - trace_sector_jump_ratio → ratio secuencial (feature 4) [invertido: jump_ratio alto = menos secuencial]
    5. iops_mean → tasa de I/O (feature 5)
    
    Nota: Si trace_avg_request_size_kb es 0 o NaN, usamos bw_mean_kbps como proxy.
    """
    features = []
    
    for _, row in df.iterrows():
        # Feature 1: Distancia promedio entre offsets (en sectores, convertir a bytes si es necesario)
        # trace_avg_sector_distance está en sectores, asumimos sector = 512 bytes
        avg_distance = float(row.get("trace_avg_sector_distance", 0.0)) * 512.0
        
        # Feature 2: Variabilidad - usar jump_ratio como proxy de variabilidad
        # Un jump_ratio alto indica más variabilidad (más saltos)
        variability = float(row.get("trace_sector_jump_ratio", 0.0))
        
        # Feature 3: Tamaño promedio de I/O
        avg_size_kb = float(row.get("trace_avg_request_size_kb", 0.0))
        if avg_size_kb <= 0 or np.isnan(avg_size_kb):
            # Fallback: estimar desde bandwidth y IOPS
            iops = float(row.get("iops_mean", 1.0))
            bw_kbps = float(row.get("bw_mean_kbps", 0.0))
            if iops > 0:
                avg_size_bytes = (bw_kbps * 1024.0) / iops
            else:
                avg_size_bytes = 0.0
        else:
            avg_size_bytes = avg_size_kb * 1024.0
        
        # Feature 4: Ratio de accesos secuenciales
        # trace_sector_jump_ratio: alto = muchos saltos = menos secuencial
        # Invertimos: 1 - jump_ratio = ratio secuencial
        jump_ratio = float(row.get("trace_sector_jump_ratio", 0.0))
        seq_ratio = max(0.0, min(1.0, 1.0 - jump_ratio))  # Clamp entre 0 y 1
        
        # Feature 5: Tasa de I/O (IOPS)
        io_rate = float(row.get("iops_mean", 0.0))
        
        features.append([avg_distance, variability, avg_size_bytes, seq_ratio, io_rate])
    
    return np.asarray(features, dtype=np.float32)


def main() -> None:
    consolidated_csv = Path("consolidated_dataset.csv")
    if not consolidated_csv.exists():
        raise FileNotFoundError(
            f"No se encontró 'consolidated_dataset.csv'. "
            "Coloca el archivo en el directorio raíz del proyecto."
        )
    
    print(f"Leyendo {consolidated_csv}...")
    df = pd.read_csv(consolidated_csv)
    
    print(f"Filas leídas: {len(df)}")
    print(f"Columnas: {list(df.columns)}")
    
    # Verificar que existe la columna 'label'
    if "label" not in df.columns:
        raise ValueError("El CSV debe tener una columna 'label' con valores: sequential, random, mixed")
    
    # Extraer características
    print("Extrayendo características...")
    X = extract_features_from_consolidated(df)
    
    # Mapear etiquetas
    print("Mapeando etiquetas...")
    y = np.array([map_label_to_int(label) for label in df["label"]], dtype=np.int64)
    
    print(f"Shape de X: {X.shape}")
    print(f"Shape de y: {y.shape}")
    print(f"Distribución de clases: {np.bincount(y)}")
    
    # Verificar valores NaN o Inf
    if np.any(np.isnan(X)) or np.any(np.isinf(X)):
        print("Advertencia: Se encontraron NaN o Inf. Reemplazando...")
        X = np.nan_to_num(X, nan=0.0, posinf=1e6, neginf=-1e6)
    
    # Split 80-20 estratificado
    print("Dividiendo en train/test (80/20)...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    
    # Normalizar
    print("Normalizando características...")
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train).astype(np.float32)
    X_test = scaler.transform(X_test).astype(np.float32)
    
    # Crear directorios
    data_processed = Path("data/processed")
    artifacts_dir = Path("artifacts")
    data_processed.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Guardar datasets
    print("Guardando datasets...")
    np.savez_compressed(data_processed / "train.npz", X=X_train, y=y_train)
    np.savez_compressed(data_processed / "test.npz", X=X_test, y=y_test)
    
    # Guardar scaler
    joblib.dump(scaler, artifacts_dir / "scaler.pkl")
    print(f"Scaler guardado en {artifacts_dir / 'scaler.pkl'}")
    
    # Guardar metadata
    metadata = {
        "num_features": int(X_train.shape[1]),
        "num_classes": int(len(np.unique(y))),
        "samples_train": int(X_train.shape[0]),
        "samples_test": int(X_test.shape[0]),
        "class_map": {"0": "sequential", "1": "random", "2": "mixed"},
        "source": "consolidated_dataset.csv",
        "feature_mapping": {
            "feature_1": "trace_avg_sector_distance * 512 (distancia promedio en bytes)",
            "feature_2": "trace_sector_jump_ratio (variabilidad)",
            "feature_3": "trace_avg_request_size_kb * 1024 (tamaño promedio I/O en bytes)",
            "feature_4": "1 - trace_sector_jump_ratio (ratio secuencial)",
            "feature_5": "iops_mean (tasa de I/O)"
        }
    }
    (artifacts_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    
    print("\n" + "="*60)
    print("Dataset procesado exitosamente!")
    print(f"  - Train: {X_train.shape[0]} muestras")
    print(f"  - Test: {X_test.shape[0]} muestras")
    print(f"  - Features: {X_train.shape[1]}")
    print(f"  - Clases: {metadata['num_classes']}")
    print(f"\nArchivos guardados:")
    print(f"  - {data_processed / 'train.npz'}")
    print(f"  - {data_processed / 'test.npz'}")
    print(f"  - {artifacts_dir / 'scaler.pkl'}")
    print(f"  - {artifacts_dir / 'metadata.json'}")
    print("="*60)
    print("\nAhora puedes ejecutar: python train.py")


if __name__ == "__main__":
    main()


