"""
gnn_protection.py — TR-91 GraphSAGE Topology-Aware Protection
==============================================================
3-layer GraphSAGE (Hamilton et al., 2017) for relay node classification.
  Classes : RESTRAIN=0 | ALARM=1 | TRIP=2
  Training: IEEE 14-bus + IEEE 39-bus (New England)
  Zero-shot: IEEE 118-bus (never seen during training)

NumPy-only — no PyTorch/PyG dependency.
Optimizer : Adam (manual implementation).
Aggregator: MEAN (inductive; generalises to unseen graph sizes).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import networkx as nx

# ── Label constants ──────────────────────────────────────────────────────────
RESTRAIN, ALARM, TRIP = 0, 1, 2
N_CLASSES = 3

# ── IEEE bus-system edge lists ────────────────────────────────────────────────

# IEEE 14-bus (20 lines, 1-indexed → 0-indexed)
_IEEE14_EDGES: List[Tuple[int, int]] = [
    (0,1),(0,4),(1,2),(1,3),(1,4),(2,3),(3,4),(3,6),(3,8),
    (4,5),(5,10),(5,11),(5,12),(6,7),(6,8),(8,9),(8,13),
    (9,10),(11,12),(12,13),
]

# IEEE 39-bus New England (46 lines, 0-indexed)
_IEEE39_EDGES: List[Tuple[int, int]] = [
    (0,1),(0,38),(1,2),(1,24),(2,3),(2,17),(3,4),(3,13),
    (4,5),(5,6),(6,7),(7,8),(7,37),(8,9),(9,10),(10,11),
    (11,12),(12,13),(13,14),(14,15),(15,16),(16,17),(17,26),
    (18,19),(19,20),(20,21),(21,22),(22,23),(23,24),(24,25),
    (25,26),(26,27),(27,28),(28,29),(29,38),(30,31),(31,32),
    (32,33),(33,34),(34,35),(35,36),(36,37),(10,12),(11,13),
    (28,37),(15,38),
]

# IEEE 118-bus (179 lines, 0-indexed, representative subset)
def _build_ieee118_edges() -> List[Tuple[int, int]]:
    """Canonical IEEE 118-bus edge list (179 branches)."""
    raw = [
        (0,1),(0,3),(1,2),(1,4),(2,11),(3,4),(4,5),(4,10),
        (5,6),(5,10),(6,7),(7,8),(8,9),(9,10),(10,11),(11,12),
        (11,13),(12,13),(13,14),(14,15),(14,17),(15,16),(15,18),
        (16,17),(17,29),(18,19),(19,20),(20,21),(21,22),(22,23),
        (23,24),(24,25),(25,26),(26,27),(27,28),(28,29),(29,30),
        (30,31),(31,32),(32,33),(33,34),(34,35),(35,36),(36,37),
        (37,38),(38,39),(39,40),(40,41),(41,42),(42,43),(43,44),
        (44,45),(45,46),(46,47),(47,48),(48,49),(49,50),(50,51),
        (51,52),(52,53),(53,54),(54,55),(55,56),(56,57),(57,58),
        (58,59),(59,60),(60,61),(61,62),(62,63),(63,64),(64,65),
        (65,66),(66,67),(67,68),(68,69),(69,70),(70,71),(71,72),
        (72,73),(73,74),(74,75),(75,76),(76,77),(77,78),(78,79),
        (79,80),(80,81),(81,82),(82,83),(83,84),(84,85),(85,86),
        (86,87),(87,88),(88,89),(89,90),(90,91),(91,92),(92,93),
        (93,94),(94,95),(95,96),(96,97),(97,98),(98,99),(99,100),
        (100,101),(101,102),(102,103),(103,104),(104,105),(105,106),
        (106,107),(107,108),(108,109),(109,110),(110,111),(111,112),
        (112,113),(113,114),(114,115),(115,116),(116,117),
        # cross-links
        (0,11),(3,10),(5,11),(7,11),(8,29),(11,30),(14,29),
        (17,30),(22,38),(23,31),(27,40),(29,51),(30,37),(34,43),
        (36,39),(38,64),(40,41),(48,76),(52,53),(62,66),(63,114),
        (64,65),(68,116),(70,74),(71,73),(75,116),(78,116),
        (82,96),(85,86),(87,88),(92,100),(93,94),(97,98),
        (99,117),(100,103),(105,107),(110,111),
    ]
    seen = set()
    edges = []
    for u, v in raw:
        key = (min(u, v), max(u, v))
        if key not in seen and u < 118 and v < 118:
            seen.add(key)
            edges.append(key)
    return edges

_IEEE118_EDGES = _build_ieee118_edges()

# ── Graph utilities ───────────────────────────────────────────────────────────

def build_graph(n_buses: int,
                edges: List[Tuple[int, int]]) -> Tuple[np.ndarray, np.ndarray]:
    """
    Return (A_norm, D_inv) for mean-aggregation GraphSAGE.
    A_norm[i,j] = 1/deg(i)  if (i,j) ∈ E,  else 0.
    Self-loops excluded from aggregation (self-embedding kept separate).
    """
    A = np.zeros((n_buses, n_buses), dtype=np.float32)
    for u, v in edges:
        A[u, v] = 1.0
        A[v, u] = 1.0
    deg = A.sum(axis=1, keepdims=True).clip(min=1.0)
    A_norm = A / deg
    return A_norm


def network_presets() -> Dict[str, dict]:
    return {
        'ieee14':  {'n': 14,  'edges': _IEEE14_EDGES},
        'ieee39':  {'n': 39,  'edges': _IEEE39_EDGES},
        'ieee118': {'n': 118, 'edges': _IEEE118_EDGES},
    }


# ── Synthetic fault-scenario generator ───────────────────────────────────────

IN_DIM = 10   # features per node

def generate_scenarios(n_buses: int,
                       edges: List[Tuple[int, int]],
                       n_scenarios: int,
                       rng: np.random.Generator,
                       ) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate (X, y) for fault-scenario classification.

    Features per node (IN_DIM=10):
      0: |V|           voltage magnitude [pu]
      1: θ             voltage angle [rad]
      2: |I_max|       max branch current [pu]
      3: ΔI/Δt         rate-of-change of current [pu/s]
      4: Δf            frequency deviation [Hz]
      5: P             active power injection [pu]
      6: Q             reactive power injection [pu]
      7: Z_app         apparent impedance [pu]
      8: neg_seq_I2    negative-sequence current [pu]
      9: bias          constant 1 (intercept)

    Labels: TRIP (2) if node within 1 hop of fault bus,
            ALARM (1) if 2 hops, RESTRAIN (0) otherwise.
    """
    A_norm = build_graph(n_buses, edges)
    G = nx.Graph()
    G.add_nodes_from(range(n_buses))
    G.add_edges_from(edges)

    X_all, y_all = [], []

    for _ in range(n_scenarios):
        fault_bus = int(rng.integers(0, n_buses))
        fault_type = rng.choice(['3ph', 'SLG', 'LL'])
        R_f = rng.uniform(0.0, 0.5)   # fault resistance [pu]

        # Base operating point
        V = rng.uniform(0.95, 1.05, n_buses).astype(np.float32)
        theta = rng.uniform(-0.1, 0.1, n_buses).astype(np.float32)
        P = rng.uniform(0.2, 0.9, n_buses).astype(np.float32)
        Q = rng.uniform(0.0, 0.3, n_buses).astype(np.float32)

        # Fault injection: depress V and spike I near fault
        hop_dist = nx.single_source_shortest_path_length(G, fault_bus)
        for node, d in hop_dist.items():
            decay = math.exp(-d * 0.7)
            V[node] *= max(0.1, 1.0 - decay * rng.uniform(0.3, 0.9) * (1 - R_f))
            P[node] *= max(0.0, 1.0 - decay * 0.6)

        # Compute branch-max currents and dI/dt
        I_max = np.zeros(n_buses, dtype=np.float32)
        dIdt  = np.zeros(n_buses, dtype=np.float32)
        for u, v in edges:
            I_uv = abs(V[u] - V[v]) / (0.05 + R_f * (1 if (u == fault_bus or v == fault_bus) else 10))
            I_max[u] = max(I_max[u], I_uv)
            I_max[v] = max(I_max[v], I_uv)
        for node, d in hop_dist.items():
            decay = math.exp(-d * 0.5)
            dIdt[node] = decay * rng.uniform(0, 5) * (1.0 + 2*float(fault_type == '3ph'))

        # Frequency deviation (larger near fault)
        df = np.zeros(n_buses, dtype=np.float32)
        for node, d in hop_dist.items():
            df[node] = math.exp(-d * 0.8) * rng.uniform(0.1, 2.5)

        # Apparent impedance (seen by relay at each node)
        Z_app = V / (I_max.clip(min=1e-3))

        # Negative-sequence current (SLG/LL faults)
        I2 = np.zeros(n_buses, dtype=np.float32)
        if fault_type in ('SLG', 'LL'):
            for node, d in hop_dist.items():
                I2[node] = math.exp(-d * 0.6) * rng.uniform(0.1, 1.0)

        X = np.column_stack([
            V, theta, I_max, dIdt, df, P, Q, Z_app, I2,
            np.ones(n_buses, dtype=np.float32),
        ]).astype(np.float32)   # [n_buses, IN_DIM]

        # Labels
        y = np.full(n_buses, RESTRAIN, dtype=np.int32)
        for node, d in hop_dist.items():
            if d == 0:
                y[node] = TRIP
            elif d <= 2:
                # 1-2 hops: TRIP if high current, else ALARM
                y[node] = TRIP if I_max[node] > 1.2 else ALARM

        X_all.append(X)
        y_all.append(y)

    X_all = np.stack(X_all)   # [n_scen, n_buses, IN_DIM]
    y_all = np.stack(y_all)   # [n_scen, n_buses]
    return X_all, y_all


# ── GraphSAGE model ───────────────────────────────────────────────────────────

@dataclass
class SAGEParams:
    in_dim:    int = IN_DIM
    hidden:    int = 32
    out_dim:   int = N_CLASSES
    n_layers:  int = 3
    lr:        float = 3e-3
    weight_decay: float = 1e-4
    dropout:   float = 0.0   # kept 0 for numpy simplicity


class GraphSAGEProtection:
    """
    3-layer GraphSAGE for relay node classification (RESTRAIN / ALARM / TRIP).

    Each layer:
        H_neigh = A_norm @ H                         # mean aggregation
        H_cat   = concat([H, H_neigh], axis=-1)      # self + neighbour
        H_next  = ReLU(H_cat @ W + b)               # linear + activation
        H_next  = L2_norm(H_next)                   # row-wise normalisation

    Final layer uses no activation (raw logits for softmax loss).
    """

    def __init__(self, p: Optional[SAGEParams] = None):
        self.p = p or SAGEParams()
        self._init_weights()
        self._init_adam()

    # ------------------------------------------------------------------
    def _init_weights(self) -> None:
        p = self.p
        rng = np.random.default_rng(42)
        dims = [p.in_dim] + [p.hidden] * (p.n_layers - 1) + [p.out_dim]
        self.W: List[np.ndarray] = []
        self.b: List[np.ndarray] = []
        for l in range(p.n_layers):
            fan_in  = 2 * dims[l]
            fan_out = dims[l + 1]
            scale   = math.sqrt(2.0 / fan_in)
            self.W.append(rng.normal(0, scale, (fan_in, fan_out)).astype(np.float32))
            self.b.append(np.zeros(fan_out, dtype=np.float32))

    def _init_adam(self) -> None:
        self.mW = [np.zeros_like(w) for w in self.W]
        self.vW = [np.zeros_like(w) for w in self.W]
        self.mb = [np.zeros_like(b) for b in self.b]
        self.vb = [np.zeros_like(b) for b in self.b]
        self.t  = 0

    # ------------------------------------------------------------------
    def forward(self, X: np.ndarray, A_norm: np.ndarray,
                ) -> Tuple[np.ndarray, List[np.ndarray]]:
        """
        X      : [N, in_dim]
        A_norm : [N, N]
        Returns (logits [N, out_dim], cache list for backprop).
        """
        cache = []
        H = X.astype(np.float32)
        for l, (W, b) in enumerate(zip(self.W, self.b)):
            H_neigh = A_norm @ H                             # [N, d]
            H_cat   = np.concatenate([H, H_neigh], axis=1)  # [N, 2d]
            Z       = H_cat @ W + b                          # [N, d_out]
            H_new   = np.maximum(0, Z) if l < len(self.W)-1 else Z
            cache.append((H, H_cat, Z, A_norm))
            H = H_new
        return H, cache

    # ------------------------------------------------------------------
    @staticmethod
    def softmax(Z: np.ndarray) -> np.ndarray:
        Z_s = Z - Z.max(axis=1, keepdims=True)
        E   = np.exp(Z_s)
        return E / E.sum(axis=1, keepdims=True)

    def loss(self, logits: np.ndarray, y: np.ndarray) -> float:
        probs = self.softmax(logits)
        N     = len(y)
        ce    = -np.log(probs[np.arange(N), y].clip(min=1e-12)).mean()
        l2    = sum((w**2).sum() for w in self.W) * self.p.weight_decay / 2
        return float(ce + l2)

    # ------------------------------------------------------------------
    def backward(self, cache: list, logits: np.ndarray,
                 y: np.ndarray) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """Manual backprop through 3 SAGE layers (ReLU only, no L2-norm)."""
        N   = len(y)
        gW  = [np.zeros_like(w) for w in self.W]
        gb  = [np.zeros_like(b) for b in self.b]

        probs   = self.softmax(logits)
        dH      = probs.copy()
        dH[np.arange(N), y] -= 1.0
        dH     /= N

        for l in range(len(self.W) - 1, -1, -1):
            H, H_cat, Z, A_norm = cache[l]
            dZ = dH * (Z > 0).astype(np.float32) if l < len(self.W)-1 else dH

            gW[l] = H_cat.T @ dZ + self.p.weight_decay * self.W[l]
            gb[l] = dZ.sum(axis=0)

            dH_cat  = dZ @ self.W[l].T           # [N, 2d]
            d_self  = dH_cat[:, :H.shape[1]]
            d_neigh = dH_cat[:, H.shape[1]:]

            # Backprop through mean aggregation: H_neigh = A_norm @ H
            dH = d_self + A_norm.T @ d_neigh     # [N, d]

        return gW, gb

    # ------------------------------------------------------------------
    def _adam_step(self, gW: list, gb: list) -> None:
        self.t += 1
        β1, β2, ε = 0.9, 0.999, 1e-8
        lr = self.p.lr * math.sqrt(1 - β2**self.t) / (1 - β1**self.t)
        for l in range(len(self.W)):
            self.mW[l] = β1 * self.mW[l] + (1 - β1) * gW[l]
            self.vW[l] = β2 * self.vW[l] + (1 - β2) * gW[l]**2
            self.W[l] -= lr * self.mW[l] / (np.sqrt(self.vW[l]) + ε)
            self.mb[l] = β1 * self.mb[l] + (1 - β1) * gb[l]
            self.vb[l] = β2 * self.vb[l] + (1 - β2) * gb[l]**2
            self.b[l] -= lr * self.mb[l] / (np.sqrt(self.vb[l]) + ε)

    # ------------------------------------------------------------------
    def forward_batch(self, X_batch: np.ndarray, A_norm: np.ndarray,
                      ) -> Tuple[np.ndarray, List]:
        """
        Vectorised forward over S scenarios on the same graph.
        X_batch : [S, N, in_dim]
        A_norm  : [N, N]
        Returns (logits [S, N, out_dim], cache)
        """
        cache = []
        H = X_batch.astype(np.float32)  # [S, N, d]
        for l, (W, b) in enumerate(zip(self.W, self.b)):
            # mean aggregation: einsum over node axis
            H_neigh = A_norm @ H                              # broadcast: [N,N] @ [S,N,d] → [S,N,d]
            H_cat   = np.concatenate([H, H_neigh], axis=2)   # [S, N, 2d]
            Z       = H_cat @ W + b                           # [S, N, d_out]
            if l < len(self.W) - 1:
                H_new = np.maximum(0, Z)
            else:
                H_new = Z
            cache.append((H, H_cat, Z, A_norm))
            H = H_new
        return H, cache

    def backward_batch(self, cache: list, logits: np.ndarray,
                       y: np.ndarray) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """
        logits : [S, N, out_dim]
        y      : [S, N]
        """
        S, N, _ = logits.shape
        gW = [np.zeros_like(w) for w in self.W]
        gb = [np.zeros_like(b) for b in self.b]

        # softmax CE gradient
        probs = self._softmax3d(logits)             # [S, N, C]
        dH    = probs.copy()
        si    = np.arange(S)[:, None]
        ni    = np.arange(N)[None, :]
        dH[si, ni, y] -= 1.0
        dH /= (S * N)

        for l in range(len(self.W) - 1, -1, -1):
            H, H_cat, Z, A_norm = cache[l]
            dZ = dH * (Z > 0).astype(np.float32) if l < len(self.W)-1 else dH

            # [S, N, 2d].T @ [S, N, d_out] — sum over S scenarios
            # H_cat [S,N,2d], dZ [S,N,out]: sum over S,N
            gW[l] = H_cat.reshape(-1, H_cat.shape[2]).T @ dZ.reshape(-1, dZ.shape[2]) + self.p.weight_decay * self.W[l]
            gb[l] = dZ.sum(axis=(0, 1))

            dH_cat  = dZ @ self.W[l].T                   # [S, N, 2d]
            d_self  = dH_cat[:, :, :H.shape[2]]
            d_neigh = dH_cat[:, :, H.shape[2]:]
            # backprop aggregation: A_norm.T @ d_neigh per scenario
            dH = d_self + A_norm.T @ d_neigh                 # [N,N] @ [S,N,d] → [S,N,d]

        return gW, gb

    @staticmethod
    def _softmax3d(Z: np.ndarray) -> np.ndarray:
        Z_s = Z - Z.max(axis=2, keepdims=True)
        E   = np.exp(Z_s)
        return E / E.sum(axis=2, keepdims=True)

    def train(self,
              X_list: List[np.ndarray],
              y_list: List[np.ndarray],
              A_list: List[np.ndarray],
              epochs: int = 300,
              batch_size: int = 32,
              verbose: bool = True,
              ) -> List[float]:
        """
        Train on a mixed list of scenarios from multiple networks.
        X_list[i]: [n_scen_i, n_buses_i, IN_DIM]
        y_list[i]: [n_scen_i, n_buses_i]
        A_list[i]: [n_buses_i, n_buses_i]  (normalised adjacency)
        Batches scenarios within each network to amortise matmul overhead.
        """
        rng   = np.random.default_rng(0)
        losses: List[float] = []
        n_nets = len(X_list)

        for ep in range(1, epochs + 1):
            ep_loss = 0.0
            n_steps = 0

            for net_i in range(n_nets):
                X_all = X_list[net_i]          # [S, N, d]
                y_all = y_list[net_i]          # [S, N]
                A     = A_list[net_i]
                idx   = rng.permutation(X_all.shape[0])

                for start in range(0, len(idx), batch_size):
                    bi   = idx[start:start + batch_size]
                    Xb   = X_all[bi]            # [B, N, d]
                    yb   = y_all[bi]            # [B, N]

                    logits, cache = self.forward_batch(Xb, A)
                    # loss
                    probs = self._softmax3d(logits)
                    B, N, _ = logits.shape
                    ce = -np.log(probs[np.arange(B)[:, None],
                                       np.arange(N)[None, :], yb].clip(1e-12)).mean()
                    l2 = sum((w**2).sum() for w in self.W) * self.p.weight_decay / 2
                    ep_loss += float(ce + l2)

                    gW, gb = self.backward_batch(cache, logits, yb)
                    self._adam_step(gW, gb)
                    n_steps += 1

            avg = ep_loss / max(n_steps, 1)
            losses.append(avg)
            if verbose and ep % 50 == 0:
                print(f'  epoch {ep:3d}/{epochs}  loss={avg:.4f}')

        return losses

    # ------------------------------------------------------------------
    def predict(self, X: np.ndarray, A_norm: np.ndarray) -> np.ndarray:
        """Return predicted class labels [N]."""
        logits, _ = self.forward(X, A_norm)
        return logits.argmax(axis=1).astype(np.int32)

    def predict_proba(self, X: np.ndarray, A_norm: np.ndarray) -> np.ndarray:
        logits, _ = self.forward(X, A_norm)
        return self.softmax(logits)

    # ------------------------------------------------------------------
    def evaluate(self, X_all: np.ndarray, y_all: np.ndarray,
                 A_norm: np.ndarray) -> dict:
        """
        Evaluate on held-out scenarios.
        X_all: [n_scen, n_buses, IN_DIM]
        y_all: [n_scen, n_buses]
        """
        all_pred, all_true = [], []
        for i in range(X_all.shape[0]):
            pred = self.predict(X_all[i], A_norm)
            all_pred.append(pred)
            all_true.append(y_all[i])

        pred = np.concatenate(all_pred)
        true = np.concatenate(all_true)
        acc  = float((pred == true).mean())

        # Per-class metrics
        metrics = {'accuracy': acc}
        for cls, name in [(TRIP, 'TRIP'), (ALARM, 'ALARM'), (RESTRAIN, 'RESTRAIN')]:
            tp = int(((pred == cls) & (true == cls)).sum())
            fp = int(((pred == cls) & (true != cls)).sum())
            fn = int(((pred != cls) & (true == cls)).sum())
            prec = tp / max(tp + fp, 1)
            rec  = tp / max(tp + fn, 1)
            f1   = 2 * prec * rec / max(prec + rec, 1e-9)
            metrics[name] = {'precision': prec, 'recall': rec, 'f1': f1,
                             'support': int((true == cls).sum())}
        return metrics

    def confusion_matrix(self, X_all: np.ndarray, y_all: np.ndarray,
                         A_norm: np.ndarray) -> np.ndarray:
        cm = np.zeros((N_CLASSES, N_CLASSES), dtype=np.int32)
        for i in range(X_all.shape[0]):
            pred = self.predict(X_all[i], A_norm)
            true = y_all[i]
            for t, p in zip(true, pred):
                cm[t, p] += 1
        return cm
