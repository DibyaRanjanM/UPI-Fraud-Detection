import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
import joblib
import os

SAVE_PATH_MODEL = os.path.join(os.path.dirname(__file__), "saved", "autoencoder.pt")
SAVE_PATH_META  = os.path.join(os.path.dirname(__file__), "saved", "autoencoder_meta.pkl")


class Autoencoder(nn.Module):
    """PDF Section 3.2.2 architecture:
       Input → Dense(64, ReLU) → Dense(32, ReLU) → Dense(16, ReLU) [bottleneck]
            → Dense(32, ReLU) → Dense(64, ReLU) → Output
    """
    def __init__(self, input_dim: int):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 64), nn.ReLU(),
            nn.Linear(64, 32),        nn.ReLU(),
            nn.Linear(32, 16),        nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(16, 32), nn.ReLU(),
            nn.Linear(32, 64), nn.ReLU(),
            nn.Linear(64, input_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))


def train(X_legit_scaled: np.ndarray, epochs: int = 30) -> dict:
    """Train autoencoder on legitimate transactions only."""
    device    = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    input_dim = X_legit_scaled.shape[1]

    X_t     = torch.FloatTensor(X_legit_scaled).to(device)
    dataset = TensorDataset(X_t, X_t)
    loader  = DataLoader(dataset, batch_size=512, shuffle=True)

    model     = Autoencoder(input_dim).to(device)
    optimizer = optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    criterion = nn.MSELoss()

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        for xb, _ in loader:
            optimizer.zero_grad()
            loss = criterion(model(xb), xb)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        if (epoch + 1) % 5 == 0:
            avg = total_loss / len(loader)
            print(f"  AE Epoch {epoch+1}/{epochs}  loss={avg:.6f}")

    # Compute p95 reconstruction error on legit data for normalisation
    model.eval()
    with torch.no_grad():
        recon  = model(X_t)
        errors = torch.mean((recon - X_t) ** 2, dim=1).cpu().numpy()
    p95 = float(np.percentile(errors, 95))

    torch.save(model.state_dict(), SAVE_PATH_MODEL)
    meta = {"p95": p95, "input_dim": input_dim}
    joblib.dump(meta, SAVE_PATH_META)
    print(f"Autoencoder saved → {SAVE_PATH_MODEL}")
    return {"model": model, "p95": p95, "device": device}


def load() -> dict:
    meta      = joblib.load(SAVE_PATH_META)
    model     = Autoencoder(meta["input_dim"])
    device    = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.load_state_dict(
        torch.load(SAVE_PATH_MODEL, map_location=device)
    )
    model.eval()
    return {"model": model, "p95": meta["p95"], "device": device}


def score(model_artifact: dict, X_scaled: np.ndarray) -> np.ndarray:
    """Return normalised reconstruction error scores in [0, 1]."""
    model  = model_artifact["model"]
    p95    = model_artifact["p95"]
    device = model_artifact["device"]

    model.eval()
    with torch.no_grad():
        t      = torch.FloatTensor(X_scaled).to(device)
        recon  = model(t)
        errors = torch.mean((recon - t) ** 2, dim=1).cpu().numpy()

    return np.clip(errors / (p95 + 1e-8), 0, 5) / 5.0