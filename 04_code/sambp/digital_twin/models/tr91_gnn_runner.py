"""TR-91 runner: train GraphSAGE on IEEE 14+39, zero-shot test on IEEE 118."""

import numpy as np
import os, sys, time, json

sys.path.insert(0, os.path.dirname(__file__))
from gnn_protection import (
    GraphSAGEProtection, SAGEParams, generate_scenarios, build_graph,
    _IEEE14_EDGES, _IEEE39_EDGES, _IEEE118_EDGES,
)

# ── output paths ───────────────────────────────────────────────────────────────
_OUT = os.path.join(
    os.path.dirname(__file__),
    "../../../../03_technical_reports/phase_8_advanced_extensions/TR91_GNN_topology",
)
os.makedirs(_OUT, exist_ok=True)

RNG = np.random.default_rng(42)

# ── network definitions ────────────────────────────────────────────────────────
NETWORKS = {
    "IEEE14":  (14,  _IEEE14_EDGES),
    "IEEE39":  (39,  _IEEE39_EDGES),
    "IEEE118": (118, _IEEE118_EDGES),
}

N_TRAIN_SCEN = 60    # per training network
N_TEST_SCEN  = 30    # held-out per training network
N_ZSHOT_SCEN = 50    # zero-shot (IEEE 118)

CLASS_NAMES = ["RESTRAIN", "ALARM", "TRIP"]


def _accuracy(pred, true):
    return float(np.mean(pred == true))


def _per_class_f1(cm):
    """Macro F1 from confusion matrix [C,C]."""
    f1s = []
    for c in range(cm.shape[0]):
        tp = cm[c, c]
        fp = cm[:, c].sum() - tp
        fn = cm[c, :].sum() - tp
        p  = tp / (tp + fp + 1e-9)
        r  = tp / (tp + fn + 1e-9)
        f1s.append(2 * p * r / (p + r + 1e-9))
    return np.array(f1s)


def run():
    print("=" * 64)
    print("TR-91  GraphSAGE topology-aware protection")
    print("=" * 64)

    # ── 1. generate data ───────────────────────────────────────────────────────
    print("\n[1/4] Generating scenarios …")
    data = {}
    for name, (n_bus, edges) in NETWORKS.items():
        A = build_graph(n_bus, edges)
        n_scen = N_ZSHOT_SCEN if name == "IEEE118" else (N_TRAIN_SCEN + N_TEST_SCEN)
        X, y = generate_scenarios(n_bus, edges, n_scen, RNG)
        data[name] = {"A": A, "X": X, "y": y, "n_bus": n_bus}
        pos = int(np.sum(y == 2))
        print(f"  {name}: {n_scen} scenarios × {n_bus} buses | "
              f"TRIP={pos} ALARM={int(np.sum(y==1))} RESTRAIN={int(np.sum(y==0))}")

    # split train / held-out test for IEEE14 and IEEE39
    X_train, y_train, A_train = [], [], []
    X_test,  y_test,  A_test  = [], [], []
    for name in ("IEEE14", "IEEE39"):
        d = data[name]
        n_tr = N_TRAIN_SCEN
        X_train.append(d["X"][:n_tr])
        y_train.append(d["y"][:n_tr])
        A_train.append(d["A"])
        X_test.append(d["X"][n_tr:])
        y_test.append(d["y"][n_tr:])
        A_test.append(d["A"])

    # ── 2. train ───────────────────────────────────────────────────────────────
    print("\n[2/4] Training GraphSAGE (100 epochs, batch=30) …")
    params = SAGEParams(in_dim=10, hidden=32, out_dim=3, n_layers=3,
                        lr=3e-3, weight_decay=1e-4)
    np.random.seed(0)
    model = GraphSAGEProtection(params)
    t0 = time.time()
    loss_hist = model.train(X_train, y_train, A_train,
                            epochs=100, batch_size=30)
    t_train = time.time() - t0
    print(f"  Training time: {t_train:.1f}s | final loss: {loss_hist[-1]:.4f}")

    # ── 3. evaluate on held-out (in-distribution) ──────────────────────────────
    print("\n[3/4] Held-out evaluation (in-distribution) …")
    results = {}
    for i, name in enumerate(("IEEE14", "IEEE39")):
        d = data[name]
        metrics = model.evaluate(X_test[i], y_test[i], A_test[i])
        acc = metrics['accuracy']
        cm = model.confusion_matrix(X_test[i], y_test[i], A_test[i])
        f1 = _per_class_f1(cm)
        results[name] = {"acc": acc, "f1": f1, "cm": cm}
        print(f"  {name}  acc={acc*100:.1f}%  "
              f"F1=[{f1[0]:.3f} {f1[1]:.3f} {f1[2]:.3f}]  macro={f1.mean():.3f}")

    # ── 4. zero-shot on IEEE 118 ───────────────────────────────────────────────
    print("\n[4/4] Zero-shot evaluation (IEEE 118, never seen) …")
    dz = data["IEEE118"]
    t_inf0 = time.time()
    metrics_z = model.evaluate(dz["X"], dz["y"], dz["A"])
    acc_z = metrics_z['accuracy']
    t_inf = (time.time() - t_inf0) / (N_ZSHOT_SCEN * 118) * 1e6  # µs/node
    cm_z = model.confusion_matrix(dz["X"], dz["y"], dz["A"])
    f1_z = _per_class_f1(cm_z)
    results["IEEE118"] = {"acc": acc_z, "f1": f1_z, "cm": cm_z}
    print(f"  IEEE118 acc={acc_z*100:.1f}%  "
          f"F1=[{f1_z[0]:.3f} {f1_z[1]:.3f} {f1_z[2]:.3f}]  macro={f1_z.mean():.3f}")
    print(f"  Inference: {t_inf:.2f} µs/node")

    # ── save artefacts ─────────────────────────────────────────────────────────
    _save_results(results, loss_hist, t_train, t_inf, params)
    print(f"\nArtefacts written to {_OUT}")
    return results, loss_hist


def _save_results(results, loss_hist, t_train, t_inf, params):
    """Write JSON + LaTeX table snippets for TR-91 report."""

    # -- JSON summary --
    summary = {
        "training_time_s": round(t_train, 1),
        "inference_us_per_node": round(t_inf, 3),
        "loss_final": round(float(loss_hist[-1]), 4),
        "networks": {
            name: {
                "accuracy": round(float(r["acc"]), 4),
                "f1_restrain": round(float(r["f1"][0]), 4),
                "f1_alarm":    round(float(r["f1"][1]), 4),
                "f1_trip":     round(float(r["f1"][2]), 4),
                "macro_f1":    round(float(r["f1"].mean()), 4),
                "confusion_matrix": r["cm"].tolist(),
            }
            for name, r in results.items()
        },
    }
    with open(os.path.join(_OUT, "tr91_results.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # -- LaTeX accuracy table --
    rows = []
    for name, r in results.items():
        tag = r"$\dagger$" if name == "IEEE118" else ""
        rows.append(
            f"    {name}{tag} & {r['acc']*100:.1f}\\% & "
            f"{r['f1'][0]:.3f} & {r['f1'][1]:.3f} & {r['f1'][2]:.3f} & "
            f"{r['f1'].mean():.3f} \\\\"
        )
    tex_acc = (
        "% AUTO-GENERATED by tr91_gnn_runner.py\n"
        "\\begin{tabular}{lrrrrr}\n"
        "\\toprule\n"
        "Network & Accuracy & F1-REST. & F1-ALARM & F1-TRIP & Macro-F1 \\\\\n"
        "\\midrule\n"
        + "\n".join(rows) + "\n"
        "\\midrule\n"
        "\\multicolumn{6}{l}{$\\dagger$ zero-shot: never seen during training} \\\\\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
    )
    with open(os.path.join(_OUT, "tab_accuracy.tex"), "w") as f:
        f.write(tex_acc)

    # -- LaTeX confusion matrix (IEEE118 only) --
    cm = results["IEEE118"]["cm"]
    cm_rows = []
    for i, row_name in enumerate(CLASS_NAMES):
        cols = " & ".join(str(cm[i, j]) for j in range(3))
        cm_rows.append(f"    {row_name} & {cols} \\\\")
    tex_cm = (
        "% AUTO-GENERATED by tr91_gnn_runner.py\n"
        "\\begin{tabular}{lrrr}\n"
        "\\toprule\n"
        "True $\\backslash$ Pred & RESTRAIN & ALARM & TRIP \\\\\n"
        "\\midrule\n"
        + "\n".join(cm_rows) + "\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
    )
    with open(os.path.join(_OUT, "tab_cm_ieee118.tex"), "w") as f:
        f.write(tex_cm)

    # -- loss curve data (for pgfplots) --
    epochs = list(range(1, len(loss_hist) + 1))
    csv_lines = ["epoch,loss"] + [f"{e},{l:.6f}" for e, l in zip(epochs, loss_hist)]
    with open(os.path.join(_OUT, "loss_curve.csv"), "w") as f:
        f.write("\n".join(csv_lines))

    print("\n  Saved: tr91_results.json, tab_accuracy.tex, tab_cm_ieee118.tex, loss_curve.csv")


if __name__ == "__main__":
    run()
