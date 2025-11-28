import json
from pathlib import Path
from typing import Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader

from neuronal_red import IOPatternClassifier


def set_seed(seed: int = 42) -> None:
    torch.manual_seed(seed)
    np.random.seed(seed)


def load_data() -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    train_npz = np.load("data/processed/train.npz")
    test_npz = np.load("data/processed/test.npz")
    return train_npz["X"], train_npz["y"], test_npz["X"], test_npz["y"]


def train_model(
    model: nn.Module,
    train_loader: DataLoader,
    X_val: torch.Tensor,
    y_val: torch.Tensor,
    epochs: int = 50,
    lr: float = 1e-3,
    device: str = "cpu",
) -> nn.Module:
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)

    best_acc = 0.0
    patience = 8
    patience_counter = 0

    model.to(device)
    X_val = X_val.to(device)
    y_val = y_val.to(device)

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        for batch_X, batch_y in train_loader:
            batch_X = batch_X.to(device)
            batch_y = batch_y.to(device)

            optimizer.zero_grad()
            logits = model(batch_X)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        # Eval
        model.eval()
        with torch.no_grad():
            logits = model(X_val)
            preds = torch.argmax(logits, dim=1)
            acc = (preds == y_val).float().mean().item()

        print(f"Epoch {epoch+1:03d} | loss={total_loss/len(train_loader):.4f} | val_acc={acc:.4f}")

        if acc > best_acc + 1e-4:
            best_acc = acc
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print("Early stopping por paciencia.")
                break

    return model


def export_model(model: nn.Module, input_size: int, artifacts_dir: Path) -> None:
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # TorchScript
    example = torch.randn(1, input_size)
    traced = torch.jit.trace(model.cpu(), example)
    traced.save(str(artifacts_dir / "model_ts.pt"))

    # ONNX
    try:
        torch.onnx.export(
            model.cpu(),
            example,
            str(artifacts_dir / "model.onnx"),
            input_names=["input"],
            output_names=["logits"],
            opset_version=12,
            dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
        )
    except Exception as e:
        print(f"Advertencia: exportación ONNX falló: {e}")


def main() -> None:
    set_seed(42)

    X_train, y_train, X_test, y_test = load_data()

    input_size = X_train.shape[1]
    num_classes = int(len(np.unique(y_train)))

    train_ds = TensorDataset(
        torch.tensor(X_train, dtype=torch.float32),
        torch.tensor(y_train, dtype=torch.long),
    )
    train_loader = DataLoader(train_ds, batch_size=128, shuffle=True)

    model = IOPatternClassifier(input_size=input_size, hidden_size=32, num_classes=num_classes)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = train_model(
        model=model,
        train_loader=train_loader,
        X_val=torch.tensor(X_test, dtype=torch.float32),
        y_val=torch.tensor(y_test, dtype=torch.long),
        epochs=60,
        lr=1e-3,
        device=device,
    )

    # Métricas finales
    model.eval()
    with torch.no_grad():
        logits = model(torch.tensor(X_test, dtype=torch.float32).to(device))
        preds = torch.argmax(logits, dim=1).cpu().numpy()
        acc = float((preds == y_test).mean())

    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True, parents=True)

    torch.save(model.state_dict(), artifacts / "model.pth")
    export_model(model, input_size, artifacts)

    summary = {
        "input_size": input_size,
        "num_classes": num_classes,
        "test_accuracy": acc,
        "class_map": {"0": "sequential", "1": "random", "2": "mixed"},
    }
    (artifacts / "training_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Entrenamiento completo. Accuracy test={acc:.4f}. Artefactos en 'artifacts/'.")


if __name__ == "__main__":
    main()




