"""
Script de ejemplo para hacer predicciones con el modelo entrenado.

Este script muestra cómo:
1. Cargar el modelo entrenado
2. Cargar el normalizador (scaler)
3. Preparar datos de entrada (las 5 características)
4. Normalizar los datos
5. Hacer la predicción
6. Interpretar los resultados
"""

import json
from pathlib import Path

import joblib
import numpy as np
import torch

from neuronal_red import IOPatternClassifier


def load_model_and_scaler():
    """Carga el modelo entrenado y el normalizador."""
    artifacts_dir = Path("artifacts")
    
    # Cargar metadatos
    with open(artifacts_dir / "metadata.json", "r") as f:
        metadata = json.load(f)
    
    # Cargar scaler (normalizador)
    scaler = joblib.load(artifacts_dir / "scaler.pkl")
    
    # Cargar modelo
    input_size = metadata["num_features"]
    num_classes = metadata["num_classes"]
    model = IOPatternClassifier(input_size=input_size, hidden_size=32, num_classes=num_classes)
    model.load_state_dict(torch.load(artifacts_dir / "model.pth", map_location="cpu"))
    model.eval()  # Modo evaluación (desactiva dropout, etc.)
    
    return model, scaler, metadata


def prepare_features_from_raw_data(
    avg_sector_distance: float,
    sector_jump_ratio: float,
    bw_mean_kbps: float,
    iops_mean: float,
    avg_request_size_kb: float = 0.0
) -> np.ndarray:
    """
    Prepara las 5 características a partir de datos raw.
    
    Parámetros:
    -----------
    avg_sector_distance : float
        Distancia promedio entre sectores (en sectores de 512 bytes)
    sector_jump_ratio : float
        Ratio de saltos grandes (>1MB) entre accesos (0.0-1.0)
    bw_mean_kbps : float
        Bandwidth promedio en KB/s
    iops_mean : float
        IOPS promedio (operaciones por segundo)
    avg_request_size_kb : float, opcional
        Tamaño promedio de request en KB. Si es 0, se calcula desde bw e iops
    
    Retorna:
    --------
    np.ndarray de shape (5,) con las características en el orden correcto
    """
    # Feature 1: Distancia promedio en bytes
    feature_1 = avg_sector_distance * 512.0
    
    # Feature 2: Variabilidad (jump ratio)
    feature_2 = sector_jump_ratio
    
    # Feature 3: Tamaño promedio de I/O en bytes
    if avg_request_size_kb > 0:
        feature_3 = avg_request_size_kb * 1024.0
    else:
        # Calcular desde bandwidth e IOPS
        if iops_mean > 0:
            feature_3 = (bw_mean_kbps * 1024.0) / iops_mean
        else:
            feature_3 = 0.0
    
    # Feature 4: Ratio secuencial (inverso del jump ratio)
    feature_4 = max(0.0, min(1.0, 1.0 - sector_jump_ratio))
    
    # Feature 5: IOPS
    feature_5 = iops_mean
    
    # Retornar como array numpy
    features = np.array([feature_1, feature_2, feature_3, feature_4, feature_5], dtype=np.float32)
    
    return features


def predict(model, scaler, features: np.ndarray, metadata: dict):
    """
    Hace una predicción con el modelo.
    
    Parámetros:
    -----------
    model : IOPatternClassifier
        Modelo entrenado
    scaler : StandardScaler
        Normalizador
    features : np.ndarray
        Array de 5 características (sin normalizar)
    metadata : dict
        Metadatos con mapeo de clases
    
    Retorna:
    --------
    dict con la predicción y probabilidades
    """
    # CRÍTICO: Normalizar las características
    features_normalized = scaler.transform(features.reshape(1, -1))
    
    # Convertir a tensor de PyTorch
    features_tensor = torch.tensor(features_normalized, dtype=torch.float32)
    
    # Hacer predicción (sin calcular gradientes)
    with torch.no_grad():
        logits = model(features_tensor)
        
        # Aplicar softmax para obtener probabilidades
        probabilities = torch.softmax(logits, dim=1)
        
        # Obtener la clase predicha (índice del máximo)
        predicted_class = torch.argmax(logits, dim=1).item()
    
    # Mapear clase numérica a nombre
    class_map = metadata["class_map"]
    predicted_label = class_map[str(predicted_class)]
    
    # Extraer probabilidades
    probs = probabilities[0].numpy()
    
    return {
        "predicted_class": predicted_class,
        "predicted_label": predicted_label,
        "probabilities": {
            "sequential": float(probs[0]),
            "random": float(probs[1]),
            "mixed": float(probs[2])
        },
        "confidence": float(probs[predicted_class])
    }


def main():
    """Ejemplo de uso del modelo para hacer predicciones."""
    
    print("=" * 60)
    print("Ejemplo de Predicción con el Modelo de I/O Patterns")
    print("=" * 60)
    
    # Cargar modelo y scaler
    print("\n1. Cargando modelo y normalizador...")
    model, scaler, metadata = load_model_and_scaler()
    print("   ✓ Modelo cargado")
    print("   ✓ Scaler cargado")
    
    # Ejemplo 1: Patrón SECUENCIAL
    print("\n" + "-" * 60)
    print("Ejemplo 1: Patrón SECUENCIAL")
    print("-" * 60)
    
    # Características típicas de un patrón secuencial (basadas en datos reales):
    # - Distancia pequeña entre sectores (ej: 200,000 sectores = ~100 MB)
    # - Bajo jump ratio (ej: 0.16 = 16%)
    # - Alto bandwidth (ej: 61,599 KB/s = ~60 MB/s)
    # - Bajo IOPS (ej: 1.0 ops/s - valor del dataset)
    
    features_seq = prepare_features_from_raw_data(
        avg_sector_distance=200000.0,   # ~200,000 sectores (basado en datos reales)
        sector_jump_ratio=0.16,          # 16% de saltos grandes (basado en datos reales)
        bw_mean_kbps=61599.0,          # ~60 MB/s (basado en datos reales)
        iops_mean=1.0                   # 1 IOPS (valor del dataset)
    )
    
    print(f"\nCaracterísticas (sin normalizar):")
    print(f"  [0] Distancia promedio: {features_seq[0]:.2f} bytes")
    print(f"  [1] Variabilidad: {features_seq[1]:.4f}")
    print(f"  [2] Tamaño promedio I/O: {features_seq[2]:.2f} bytes")
    print(f"  [3] Ratio secuencial: {features_seq[3]:.4f}")
    print(f"  [4] IOPS: {features_seq[4]:.2f}")
    
    result_seq = predict(model, scaler, features_seq, metadata)
    
    print(f"\nPredicción:")
    print(f"  Clase: {result_seq['predicted_class']} ({result_seq['predicted_label']})")
    print(f"  Confianza: {result_seq['confidence']*100:.2f}%")
    print(f"\nProbabilidades:")
    for label, prob in result_seq['probabilities'].items():
        print(f"  {label:12s}: {prob*100:6.2f}%")
    
    # Ejemplo 2: Patrón ALEATORIO
    print("\n" + "-" * 60)
    print("Ejemplo 2: Patrón ALEATORIO")
    print("-" * 60)
    
    # Características típicas de un patrón aleatorio (basadas en datos reales):
    # - Distancia grande entre sectores (ej: 18,714,350 sectores = ~9.5 GB)
    # - Alto jump ratio (ej: 0.98 = 98%)
    # - Bajo bandwidth (ej: 7,814 KB/s = ~7.8 MB/s)
    # - Bajo IOPS (ej: 1.0 ops/s - valor del dataset)
    
    features_rand = prepare_features_from_raw_data(
        avg_sector_distance=18714350.0, # ~18.7M sectores (basado en datos reales)
        sector_jump_ratio=0.98,          # 98% de saltos grandes (basado en datos reales)
        bw_mean_kbps=7814.0,            # ~7.8 MB/s (basado en datos reales)
        iops_mean=1.0                    # 1 IOPS (valor del dataset)
    )
    
    print(f"\nCaracterísticas (sin normalizar):")
    print(f"  [0] Distancia promedio: {features_rand[0]:.2f} bytes")
    print(f"  [1] Variabilidad: {features_rand[1]:.4f}")
    print(f"  [2] Tamaño promedio I/O: {features_rand[2]:.2f} bytes")
    print(f"  [3] Ratio secuencial: {features_rand[3]:.4f}")
    print(f"  [4] IOPS: {features_rand[4]:.2f}")
    
    result_rand = predict(model, scaler, features_rand, metadata)
    
    print(f"\nPredicción:")
    print(f"  Clase: {result_rand['predicted_class']} ({result_rand['predicted_label']})")
    print(f"  Confianza: {result_rand['confidence']*100:.2f}%")
    print(f"\nProbabilidades:")
    for label, prob in result_rand['probabilities'].items():
        print(f"  {label:12s}: {prob*100:6.2f}%")
    
    # Ejemplo 3: Patrón MIXTO
    print("\n" + "-" * 60)
    print("Ejemplo 3: Patrón MIXTO")
    print("-" * 60)
    
    # Características típicas de un patrón mixto (basadas en datos reales):
    # - Distancia intermedia (ej: 12,951,950 sectores = ~6.6 GB)
    # - Jump ratio alto (ej: 0.97 = 97%)
    # - Bandwidth medio (ej: 38,289 KB/s = ~38 MB/s)
    # - IOPS bajo (ej: 1.0 ops/s - valor del dataset)
    
    features_mixed = prepare_features_from_raw_data(
        avg_sector_distance=12951950.0,  # ~13M sectores (basado en datos reales)
        sector_jump_ratio=0.97,          # 97% de saltos grandes (basado en datos reales)
        bw_mean_kbps=38289.0,           # ~38 MB/s (basado en datos reales)
        iops_mean=1.0                    # 1 IOPS (valor del dataset)
    )
    
    print(f"\nCaracterísticas (sin normalizar):")
    print(f"  [0] Distancia promedio: {features_mixed[0]:.2f} bytes")
    print(f"  [1] Variabilidad: {features_mixed[1]:.4f}")
    print(f"  [2] Tamaño promedio I/O: {features_mixed[2]:.2f} bytes")
    print(f"  [3] Ratio secuencial: {features_mixed[3]:.4f}")
    print(f"  [4] IOPS: {features_mixed[4]:.2f}")
    
    result_mixed = predict(model, scaler, features_mixed, metadata)
    
    print(f"\nPredicción:")
    print(f"  Clase: {result_mixed['predicted_class']} ({result_mixed['predicted_label']})")
    print(f"  Confianza: {result_mixed['confidence']*100:.2f}%")
    print(f"\nProbabilidades:")
    for label, prob in result_mixed['probabilities'].items():
        print(f"  {label:12s}: {prob*100:6.2f}%")
    
    print("\n" + "=" * 60)
    print("Nota: Las características deben calcularse sobre una ventana")
    print("      de operaciones de I/O (ej: últimas 32 operaciones)")
    print("=" * 60)


if __name__ == "__main__":
    main()

