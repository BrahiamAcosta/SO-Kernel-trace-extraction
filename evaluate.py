import json
from pathlib import Path

import numpy as np
import torch

from neuronal_red import IOPatternClassifier


def main() -> None:
    test_npz = np.load("data/processed/test.npz")
    X_test = torch.tensor(test_npz["X"], dtype=torch.float32)
    y_test = test_npz["y"]

    artifacts = Path("artifacts")
    state_path = artifacts / "model.pth"

    if not state_path.exists():
        raise SystemExit("No se encontró artifacts/model.pth. Entrena primero con train.py.")

    input_size = X_test.shape[1]
    model = IOPatternClassifier(input_size=input_size, hidden_size=32, num_classes=3)
    model.load_state_dict(torch.load(state_path, map_location="cpu"))
    model.eval()

    with torch.no_grad():
        logits = model(X_test)
        preds = torch.argmax(logits, dim=1).numpy()

    acc = float((preds == y_test).mean())
    print(f"Accuracy test: {acc:.4f}")

    # Matriz de confusión simple
    cm = np.zeros((3, 3), dtype=int)
    for t, p in zip(y_test, preds):
        cm[int(t), int(p)] += 1
    print("Matriz de confusión (filas=verdadero, columnas=predicho):")
    print(cm)

    (artifacts / "eval_summary.json").write_text(
        json.dumps({"accuracy": acc, "confusion_matrix": cm.tolist()}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()




