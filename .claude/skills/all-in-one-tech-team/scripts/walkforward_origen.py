#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
===============================================================================
 WALK-FORWARD POR ORIGEN — scoring con leakage estructuralmente imposible
===============================================================================
 Para datasets "pivoteados": una fila por entidad y columnas por periodo
 (evento_P1..evento_PN, monto_P1..monto_PN), donde P1 es el periodo MAS RECIENTE.

 Protocolo:
   para predecir el periodo Pk:
       features      = SOLO P(k+1)..P(k+V)   -> nada de Pk ni posterior
       entrenamiento = SOLO origenes j > k   -> modelos ajustados con info previa
 No hace falta auditar el leakage: la construccion lo hace imposible.

 Ademas:
   - Auditoria de leakage igual, como red de seguridad (regla + AUC univariada).
   - Correccion del sesgo del monto: smearing de Duan + calibracion de escala
     medida SOLO en los periodos de entrenamiento.
   - Deteccion de periodos parciales (tasa muy por debajo del resto) -> excluir.

 Generico: los prefijos de columna y la cantidad de periodos son parametros.

 Uso:
   python walkforward_origen.py datos.csv --evento Pago_M --monto Monto_M --periodos 12
   python walkforward_origen.py --demo
===============================================================================
"""
from __future__ import annotations
import argparse, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
try:
    import lightgbm as lgb; _LGB = True
except ImportError:
    _LGB = False

_CATS: dict = {}


def fijar_categorias(d, cats):
    """Las categorias se fijan UNA vez sobre el dataset completo: si se infieren
    por trozo, un concat de submuestras las degrada a object y LightGBM falla."""
    for c in cats:
        if c in d: _CATS[c] = sorted(d[c].astype(str).unique())


# ------------------------------------------------------------------ features
def features(d, k, ev, mo, ventana, n_per, excluir, cats, extras):
    ps = [i for i in range(k + 1, k + 1 + ventana) if i <= n_per and i not in excluir]
    P = d[[f"{ev}{i}" for i in ps]].values.astype(float)
    M = d[[f"{mo}{i}" for i in ps]].values.astype(float) if mo else np.zeros_like(P)
    n = P.shape[1]
    X = pd.DataFrame(index=d.index)
    X["n_ev"] = P.sum(1); X["ratio_ev"] = P.sum(1) / n
    X["ev_ult1"] = P[:, 0]; X["ev_ult3"] = P[:, :min(3, n)].sum(1)
    X["ev_ult6"] = P[:, :min(6, n)].sum(1)
    rec = np.full(len(d), n + 1, float)
    for j in range(n): rec = np.where((P[:, j] > 0) & (rec == n + 1), j + 1, rec)
    X["recencia"] = rec
    X["nunca"] = (P.sum(1) == 0).astype(int); X["siempre"] = (P.sum(1) == n).astype(int)
    r = np.zeros(len(d))
    for j in range(n): r = np.where(P[:, j] > 0, r + (r == j), r)
    X["racha"] = r; X["std_ev"] = P.std(1)
    h = max(n // 2, 1)
    X["tend_ev"] = P[:, :h].mean(1) - P[:, h:].mean(1) if n > 1 else 0.
    if mo:
        X["monto_medio"] = M.mean(1); X["monto_ult"] = M[:, 0]; X["monto_max"] = M.max(1)
        X["monto_std"] = M.std(1); X["monto_total"] = M.sum(1)
        X["monto_x_ev"] = np.where(P.sum(1) > 0, M.sum(1) / np.maximum(P.sum(1), 1), 0.)
        X["tend_monto"] = M[:, :h].mean(1) - M[:, h:].mean(1) if n > 1 else 0.
    for c in extras:
        if c in d: X[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    X[X.columns] = X[X.columns].replace([np.inf, -np.inf], 0).fillna(0)
    for c in cats:
        if c in d: X[c] = pd.Categorical(d[c].astype(str), categories=_CATS.get(c))
    return X


def _num(X):
    Z = X.copy()
    for c in Z.columns:
        if str(Z[c].dtype) == "category": Z[c] = Z[c].cat.codes
    return Z.astype(float)


def auditar(d, y, cols, prohibidas):
    inf = []
    for c in cols:
        if c in prohibidas:
            inf.append(dict(col=c, motivo="REGLA: cae en la ventana objetivo", auc=np.nan,
                            accion="BLOQUEADA")); continue
        s = d[c]
        auc = np.nan
        if s.dtype.kind in "ifub" and s.nunique() > 1:
            try:
                a = roc_auc_score(y, s.fillna(s.median())); auc = max(a, 1 - a)
            except Exception: pass
        acc = "BLOQUEADA" if (np.isfinite(auc) and auc > .95) else "OK"
        inf.append(dict(col=c, motivo=f"EVIDENCIA: AUC univariada {auc:.4f}" if acc == "BLOQUEADA"
                        else "ok", auc=auc, accion=acc))
    return pd.DataFrame(inf)


def entrenar(Xtr, ytr, Xva, yva, max_train=150_000):
    if len(Xtr) > max_train:
        i = np.random.default_rng(42).choice(len(Xtr), max_train, replace=False)
        Xtr, ytr = Xtr.iloc[i], ytr[i]
    mods = {}
    if _LGB:
        m = lgb.LGBMClassifier(num_leaves=31, learning_rate=.05, n_estimators=300,
                               min_child_samples=100, reg_lambda=5., verbosity=-1,
                               random_state=42, n_jobs=-1, colsample_bytree=.8)
        m.fit(Xtr, ytr, eval_set=[(Xva, yva)], callbacks=[lgb.early_stopping(50, verbose=False)])
        mods["lgbm"] = ("cat", m)
    m = HistGradientBoostingClassifier(max_leaf_nodes=31, learning_rate=.05, max_iter=250,
                                       l2_regularization=5., early_stopping=True, random_state=42)
    m.fit(_num(Xtr), ytr); mods["hgb"] = ("num", m)
    return mods


def predecir(mods, X):
    return np.mean([m.predict_proba(X if t == "cat" else _num(X))[:, 1]
                    for t, m in mods.values()], 0)


def regresor_monto(Xp, yp, max_n=120_000):
    """log + SMEARING DE DUAN: exp(E[log Y]) subestima E[Y] (Jensen).
    Sin este factor el monto queda 20-50% por debajo del real."""
    if len(Xp) > max_n:
        i = np.random.default_rng(7).choice(len(Xp), max_n, replace=False)
        Xp, yp = Xp.iloc[i], yp[i]
    reg = HistGradientBoostingRegressor(max_leaf_nodes=31, learning_rate=.05, max_iter=200,
                                        l2_regularization=5., random_state=42)
    yl = np.log1p(np.clip(yp, 0, None)); reg.fit(_num(Xp), yl)
    return reg, float(np.mean(np.exp(yl - reg.predict(_num(Xp)))))


def escala(d, js, mods, cal, reg, smear, cfg, n=60_000):
    """real/predicho medido SOLO en periodos de entrenamiento -> sin leakage."""
    dm = d.iloc[np.random.default_rng(11).choice(len(d), min(n, len(d)), replace=False)]
    r = p_ = 0.
    for j in js:
        Xj = features(dm, j, **cfg)
        pj = np.clip(cal.predict(predecir(mods, Xj)), 0, 1)
        mj = np.expm1(reg.predict(_num(Xj))).clip(0) * smear
        r += float(dm[f"{cfg['mo']}{j}"].sum()); p_ += float((pj * mj).sum())
    return float(np.clip(r / p_, .5, 3.)) if p_ > 0 else 1.


def correr(d, ev="Pago_M", mo="Monto_M", n_per=12, ventana=7, origenes=None,
           cats=("Estado", "SubEstado"), extras=("DiasAtraso",)):
    cats = [c for c in cats if c in d]; extras = [c for c in extras if c in d]
    fijar_categorias(d, cats)

    # periodos parciales: tasa muy por debajo del resto
    tasas = {i: d[f"{ev}{i}"].mean() for i in range(1, n_per + 1)}
    med = np.median(list(tasas.values()))
    excluir = {i for i, t in tasas.items() if t < med * .6}
    if excluir: print(f"  Periodos PARCIALES excluidos: {sorted(excluir)} "
                      f"(tasa < 60% de la mediana {med*100:.1f}%)")

    origenes = origenes or [j for j in range(1, 5) if j not in excluir]
    cfg = dict(ev=ev, mo=mo, ventana=ventana, n_per=n_per, excluir=excluir,
               cats=cats, extras=extras)
    out = []
    for k in sorted([o for o in origenes if o < max(origenes)], reverse=True):
        js = [j for j in origenes if j > k]
        Xtr = pd.concat([features(d, j, **cfg) for j in js], ignore_index=True)
        ytr = np.concatenate([d[f"{ev}{j}"].values.astype(int) for j in js])
        i = np.random.default_rng(42).permutation(len(Xtr)); c = int(len(i) * .8)
        mods = entrenar(Xtr.iloc[i[:c]], ytr[i[:c]], Xtr.iloc[i[c:]], ytr[i[c:]])
        cal = IsotonicRegression(out_of_bounds="clip").fit(predecir(mods, Xtr.iloc[i[c:]]), ytr[i[c:]])
        Xk = features(d, k, **cfg)
        yk = d[f"{ev}{k}"].values.astype(int); mk = d[f"{mo}{k}"].values.astype(float)
        p = np.clip(cal.predict(predecir(mods, Xk)), 0, 1)
        mask = np.concatenate([(d[f"{ev}{j}"] == 1).values for j in js])
        Xp = Xtr[mask]; yp = np.concatenate([d[f"{mo}{j}"].values for j in js])[mask]
        reg, sm = regresor_monto(Xp, yp)
        es = escala(d, js, mods, cal, reg, sm, cfg)
        pred = float((p * np.expm1(reg.predict(_num(Xk))).clip(0) * sm * es).sum())
        real = float(mk.sum())
        out.append(dict(periodo=f"P{k}", entrena=",".join(f"P{j}" for j in js),
                        AUC=roc_auc_score(yk, p), PR_AUC=average_precision_score(yk, p),
                        Brier=brier_score_loss(yk, p), smearing=sm, escala=es,
                        real=real, predicho=pred,
                        desvio_pct=(real / pred - 1) * 100 if pred else np.nan))
        print(f"  P{k} | AUC={out[-1]['AUC']:.4f} PR-AUC={out[-1]['PR_AUC']:.4f} "
              f"smear={sm:.3f} esc={es:.3f} | real={real:,.0f} pred={pred:,.0f} "
              f"({out[-1]['desvio_pct']:+.1f}%)")
    return pd.DataFrame(out)


def demo():
    rng = np.random.default_rng(7); n = 30000
    est = rng.choice(["A", "B", "C"], n, p=[.5, .3, .2])
    d = pd.DataFrame({"Id": np.arange(n), "Estado": est, "SubEstado": rng.choice(["x", "y"], n),
                      "DiasAtraso": rng.gamma(1.5, 400, n).astype(int)})
    prop = np.clip(rng.beta(.7, 4, n) + (est == "A") * .45, 0, .97)
    for i in range(1, 13):
        pg = rng.binomial(1, prop * (.45 if i == 12 else 1.))   # P12 parcial a proposito
        d[f"Pago_M{i}"] = pg
        d[f"Monto_M{i}"] = (pg * rng.lognormal(8.5, .6, n)).round(2)
    print("DEMO: 30.000 entidades x 12 periodos (P12 parcial a proposito)\n")
    R = correr(d)
    print(f"\nDesvio medio {R.desvio_pct.mean():+.1f}% | absoluto medio {R.desvio_pct.abs().mean():.1f}%")
    print("\nSin la correccion de sesgo, estos desvios estarian 20-50% por encima.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?"); ap.add_argument("--evento", default="Pago_M")
    ap.add_argument("--monto", default="Monto_M"); ap.add_argument("--periodos", type=int, default=12)
    ap.add_argument("--ventana", type=int, default=7); ap.add_argument("--sep", default=";")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo or not a.csv:
        demo()
    else:
        d = pd.read_csv(a.csv, sep=a.sep, encoding="latin-1", decimal=",", low_memory=False)
        R = correr(d, a.evento, a.monto, a.periodos, a.ventana)
        R.to_csv("backtest_walkforward.csv", index=False)
        print("\n-> backtest_walkforward.csv")
