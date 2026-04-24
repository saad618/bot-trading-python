import io
import json
import base64
import logging
import numpy as np

logger = logging.getLogger(__name__)

MIN_SAMPLES = 30

_model = None
_feature_keys: list = []
_model_meta: dict = {}


def _load():
    global _model, _feature_keys, _model_meta
    if _model is not None:
        return
    try:
        import joblib
        from database import get_setting
        raw = get_setting("ml_model_pkl")
        if not raw:
            return
        bundle = joblib.load(io.BytesIO(base64.b64decode(raw)))
        _model = bundle["model"]
        _feature_keys = bundle["feature_keys"]
        _model_meta = bundle.get("meta", {})
        logger.info(f"[ML] Model loaded — {_model_meta.get('samples', '?')} samples, "
                    f"win_rate={_model_meta.get('win_rate_pct', '?')}%")
    except Exception as e:
        logger.error(f"[ML] Failed to load model: {e}")


def _save_model(bundle: dict):
    """Serialize model to bytes and store in app_settings (survives Postgres redeploys)."""
    import joblib
    from database import set_setting
    buf = io.BytesIO()
    joblib.dump(bundle, buf)
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
    set_setting("ml_model_pkl", encoded)


def get_status() -> dict:
    _load()
    if _model is None:
        return {
            "trained": False,
            "message": f"Needs {MIN_SAMPLES}+ closed trades with recorded scores to train",
        }
    return {"trained": True, **_model_meta}


def predict(scores: dict) -> float | None:
    """Return win probability [0.0–1.0], or None when model is not ready."""
    _load()
    if _model is None or not _feature_keys:
        return None
    try:
        X = [[scores.get(k, 0) for k in _feature_keys]]
        return float(_model.predict_proba(X)[0][1])
    except Exception as e:
        logger.warning(f"[ML] Prediction error: {e}")
        return None


def train_from_samples(samples: list) -> dict:
    """Train directly from (breakdown_dict, win_int) pairs — used with backtest data."""
    import joblib
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score

    if len(samples) < MIN_SAMPLES:
        return {"status": "skipped", "samples": len(samples), "needed": MIN_SAMPLES}

    keys = sorted(samples[0][0].keys())
    X = [[row[0].get(k, 0) for k in keys] for row in samples]
    y = [row[1] for row in samples]

    model = GradientBoostingClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42
    )

    cv_acc = None
    if len(X) >= 50:
        cv_scores = cross_val_score(model, X, y, cv=5, scoring="accuracy")
        cv_acc = round(float(np.mean(cv_scores)) * 100, 1)

    model.fit(X, y)

    importance = {k: round(float(v), 4) for k, v in zip(keys, model.feature_importances_)}
    top_features = sorted(importance.items(), key=lambda x: -x[1])[:3]

    meta = {
        "samples":        len(samples),
        "win_rate_pct":   round(sum(y) / len(y) * 100, 1),
        "cv_accuracy_pct": cv_acc,
        "feature_keys":   keys,
        "top_features":   dict(top_features),
        "source":         "backtest",
    }

    _save_model({"model": model, "feature_keys": keys, "meta": meta})

    global _model, _feature_keys, _model_meta
    _model = model
    _feature_keys = keys
    _model_meta = meta

    logger.info(f"[ML] Trained from backtest — {len(samples)} samples, "
                f"cv_acc={cv_acc}%, top={top_features[:2]}")
    return {"status": "trained", **meta}


def retrain(db) -> dict:
    """Pull all closed positions that have entry_scores, fit the classifier, save to DB."""
    from models import OpenPosition, PositionStatus
    import joblib
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score

    closed = (
        db.query(OpenPosition)
        .filter(
            OpenPosition.status != PositionStatus.OPEN,
            OpenPosition.entry_scores.isnot(None),
            OpenPosition.exit_pnl.isnot(None),
        )
        .all()
    )

    if len(closed) < MIN_SAMPLES:
        logger.info(f"[ML] Retrain skipped — only {len(closed)} labeled samples (need {MIN_SAMPLES})")
        return {"status": "skipped", "samples": len(closed), "needed": MIN_SAMPLES}

    rows = []
    for pos in closed:
        try:
            scores = json.loads(pos.entry_scores)
            rows.append((scores, 1 if pos.exit_pnl > 0 else 0))
        except Exception:
            continue

    if len(rows) < MIN_SAMPLES:
        return {"status": "skipped", "samples": len(rows), "needed": MIN_SAMPLES}

    keys = sorted(rows[0][0].keys())
    X = [[r[0].get(k, 0) for k in keys] for r in rows]
    y = [r[1] for r in rows]

    model = GradientBoostingClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42
    )

    cv_acc = None
    if len(X) >= 50:
        cv_scores = cross_val_score(model, X, y, cv=5, scoring="accuracy")
        cv_acc = round(float(np.mean(cv_scores)) * 100, 1)

    model.fit(X, y)

    importance = {k: round(float(v), 4) for k, v in zip(keys, model.feature_importances_)}
    top_features = sorted(importance.items(), key=lambda x: -x[1])[:3]

    meta = {
        "samples": len(rows),
        "win_rate_pct": round(sum(y) / len(y) * 100, 1),
        "cv_accuracy_pct": cv_acc,
        "feature_keys": keys,
        "top_features": dict(top_features),
    }

    _save_model({"model": model, "feature_keys": keys, "meta": meta})

    global _model, _feature_keys, _model_meta
    _model = model
    _feature_keys = keys
    _model_meta = meta

    logger.info(f"[ML] Retrained — {meta['samples']} samples, "
                f"cv_acc={cv_acc}%, top={top_features[:2]}")
    return {"status": "trained", **meta}
