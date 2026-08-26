import base64
import io
import json
import logging
import os
from typing import List, Optional

import dice_ml
import joblib
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server rendering
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import shap
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sklearn.metrics import confusion_matrix, roc_curve, roc_auc_score

logger = logging.getLogger(__name__)

# Called by the Java backend (service.MLPredictionService) on: case open,
# document submission, document verification. Never called directly by the
# frontend. All paths are relative to this file's directory so it can be
# started from any working directory (see run instructions in README).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.environ.get("KYC_MODEL_PATH", os.path.join(BASE_DIR, "kyc_model.pkl"))
TRAIN_DATA_PATH = os.environ.get("KYC_TRAIN_DATA_PATH", os.path.join(BASE_DIR, "kyc_train_data.pkl"))

# Must match the encodings used when training the model (see analysis.ipynb).
INCOME_MAP = {"<25K": 0, "25-50K": 1, "50-100K": 2, "100-250K": 3, "250K+": 4}
RISK_MAP = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

# Only these fields are realistically actionable by a client trying to move
# from REJECTED to APPROVED (identity/demographic fields are locked out of DiCE).
ACTIONABLE_FEATURES = [
    "verified_docs_count",
    "expired_docs_count",
    "has_unverified_docs",
    "annual_income_band_encoded",
]

app = FastAPI(title="KYC ML & XAI Engine")

# Add exception handler for validation errors to log raw request details
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    try:
        body = await request.body()
        logger.error(f"RequestValidationError: {exc.errors()} | Raw body: {body.decode('utf-8')}")
    except Exception as e:
        logger.error(f"RequestValidationError: {exc.errors()} | Failed to read body: {e}")
    raise HTTPException(status_code=422, detail=exc.errors())

# Load artifacts
pipeline = joblib.load(MODEL_PATH)
clf = pipeline.named_steps["classifier"]
preprocessor = pipeline.named_steps["preprocessor"]

# Training data (raw, pre-preprocessing) is required by DiCE to know the valid
# range/categories for each feature. Saved alongside the model - see the
# "Persist artifacts for the FastAPI service" cell at the end of analysis.ipynb.
_train_bundle = joblib.load(TRAIN_DATA_PATH)
X_train = _train_bundle["X_train"]
y_train = _train_bundle["y_train"]
# Only present if the notebook's persist cell was re-run after adding them;
# powers the /eval/* plots below (older kyc_train_data.pkl files won't have these).
X_test = _train_bundle.get("X_test")
y_test = _train_bundle.get("y_test")

_dice_data = dice_ml.Data(
    dataframe=pd.concat([X_train, y_train], axis=1),
    continuous_features=[
        "age",
        "adverse_media_hits",
        "total_docs_submitted",
        "verified_docs_count",
        "expired_docs_count",
        "annual_income_band_encoded",
        "jurisdiction_risk_encoded",
    ],
    outcome_name="is_approved",
)
_dice_model = dice_ml.Model(model=pipeline, backend="sklearn")
_dice_explainer = dice_ml.Dice(_dice_data, _dice_model, method="random")


class CaseFeatures(BaseModel):
    client_type: Optional[str] = "INDIVIDUAL"
    nationality: Optional[str] = "GB"
    jurisdiction_risk: Optional[str] = "LOW"
    age: int = 30
    annual_income_band: Optional[str] = "50-100K"
    main_source_of_funds: Optional[str] = "Employment Income"
    is_pep: int = 0
    adverse_media_hits: int = 0
    is_cross_border: int = 0
    product_type: Optional[str] = "STANDARD"
    total_docs_submitted: int = 0
    verified_docs_count: int = 0
    expired_docs_count: int = 0
    has_unverified_docs: int = 0


class Recommendation(BaseModel):
    feature: str
    current_value: str
    suggested_value: str


class PredictionResponse(BaseModel):
    decision: str
    approval_probability: float
    # Only populated when decision == "REJECTED".
    recommendations: Optional[List[Recommendation]] = None


def _encode(features: CaseFeatures) -> pd.DataFrame:
    row = features.model_dump() if hasattr(features, "model_dump") else features.dict()
    row["annual_income_band_encoded"] = INCOME_MAP.get(row.pop("annual_income_band") or "50-100K", 1)
    row["jurisdiction_risk_encoded"] = RISK_MAP.get(row.pop("jurisdiction_risk") or "LOW", 0)
    # Ensure fallback strings for LightGBM/DiCE
    row["client_type"] = row["client_type"] or "INDIVIDUAL"
    row["nationality"] = row["nationality"] or "GB"
    row["main_source_of_funds"] = row["main_source_of_funds"] or "Employment Income"
    row["product_type"] = row["product_type"] or "STANDARD"
    return pd.DataFrame([row])[list(X_train.columns)]

def plot_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    img_str = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f"data:image/png;base64,{img_str}"


def _generate_recommendations(df_raw: pd.DataFrame) -> Optional[List[Recommendation]]:
    """Uses DiCE to find the smallest change to client-actionable fields
    (document verification/expiry, income evidence) that flips the model's
    prediction from REJECTED to APPROVED."""
    try:
        logger.info("Generating DiCE recommendations for REJECTED case")
        cf = _dice_explainer.generate_counterfactuals(
            df_raw,
            total_CFs=3,
            desired_class=1,
            features_to_vary=ACTIONABLE_FEATURES,
        )
        cf_df = cf.cf_examples_list[0].final_cfs_df
        if cf_df is None or cf_df.empty:
            logger.info("DiCE returned no counterfactuals (case may already be at limit)")
            return None
        original = df_raw.iloc[0]
        best = cf_df.iloc[0]
        recommendations = [
            Recommendation(feature=col, current_value=str(original[col]), suggested_value=str(best[col]))
            for col in ACTIONABLE_FEATURES
            if col in best and str(best[col]) != str(original[col])
        ]
        logger.info(f"Generated {len(recommendations)} recommendations: {recommendations}")
        return recommendations or None
    except Exception as e:
        # DiCE can fail to find a feasible counterfactual (e.g. already at the
        # limit of actionable fields) - treat as "no recommendation available".
        logger.warning(f"DiCE recommendation generation failed: {e}")
        return None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/debug/echo")
async def debug_echo(request: Request):
    """Debug endpoint to echo back raw request body and headers"""
    try:
        body = await request.body()
        body_str = body.decode('utf-8')
        headers = dict(request.headers)
        logger.info(f"DEBUG ECHO - Headers: {headers}")
        logger.info(f"DEBUG ECHO - Body: {body_str}")
        return {
            "headers": headers,
            "body": body_str,
            "body_length": len(body),
            "message": "Raw request echoed for debugging"
        }
    except Exception as e:
        logger.error(f"Debug echo error: {e}")
        return {"error": str(e)}


@app.post("/api/v1/predict-and-explain", response_model=PredictionResponse)
def predict_and_explain(features: CaseFeatures):
    try:
        df_raw = _encode(features)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid input: {exc}")

    pred = int(pipeline.predict(df_raw)[0])
    proba = float(pipeline.predict_proba(df_raw)[0][1])
    decision = "APPROVED" if pred == 1 else "REJECTED"

    recommendations = _generate_recommendations(df_raw) if decision == "REJECTED" else None
    
    logger.info(f"Prediction result: decision={decision}, proba={proba:.4f}, has_recommendations={recommendations is not None}")
    if recommendations:
        logger.info(f"Recommendations: {[{'feature': r.feature, 'current': r.current_value, 'suggested': r.suggested_value} for r in recommendations]}")

    return PredictionResponse(
        decision=decision,
        approval_probability=round(proba, 4),
        recommendations=recommendations,
    )


@app.post("/api/v1/explain/shap-plot")
def shap_plot(features: CaseFeatures):
    """Optional debugging endpoint - returns a base64 PNG of the local SHAP
    bar plot for a single case. Not called by the Java backend."""
    df_raw = _encode(features)
    transformed = preprocessor.transform(df_raw)
    feat_names = preprocessor.get_feature_names_out()
    explainer = shap.TreeExplainer(clf)
    shap_values = explainer.shap_values(transformed)
    shap_target = shap_values[1] if isinstance(shap_values, list) else shap_values

    fig, ax = plt.subplots(figsize=(8, 4))
    shap.bar_plot(shap_target[0], feature_names=feat_names, max_display=6, show=False)
    return {"shap_waterfall_plot": plot_to_base64(fig)}


@app.get("/api/v1/explain/feature-importance-plot")
def feature_importance_plot():
    """Debugging endpoint mirroring the "Top N Features by Information Gain"
    bar plot from analysis.ipynb. Not called by the Java backend."""
    raw_names = preprocessor.get_feature_names_out()
    clean_names = [name.split("__")[-1] for name in raw_names]
    importances = clf.booster_.feature_importance(importance_type="gain")

    importance_df = (
        pd.DataFrame({"Feature": clean_names, "Gain": importances})
        .sort_values(by="Gain", ascending=False)
        .head(10)
    )

    fig, ax = plt.subplots(figsize=(9, 5))
    sns.barplot(data=importance_df, x="Gain", y="Feature", hue="Feature", legend=False, palette="viridis", ax=ax)
    ax.set_title("Top 10 Features by Information Gain")
    fig.tight_layout()
    return {"feature_importance_plot": plot_to_base64(fig)}


@app.get("/api/v1/eval/confusion-matrix-plot")
def confusion_matrix_plot():
    """Debugging endpoint mirroring the confusion matrix plot from
    analysis.ipynb, computed on the held-out test split. Not called by the
    Java backend."""
    if X_test is None or y_test is None:
        raise HTTPException(status_code=404, detail="No test data persisted in kyc_train_data.pkl")

    y_pred = pipeline.predict(X_test)
    cm = confusion_matrix(y_test, y_pred)

    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["REJECTED", "APPROVED"],
        yticklabels=["REJECTED", "APPROVED"],
        ax=ax,
    )
    ax.set_title("Confusion Matrix")
    ax.set_ylabel("Actual Status")
    ax.set_xlabel("Predicted Status")
    fig.tight_layout()
    return {"confusion_matrix_plot": plot_to_base64(fig)}


@app.get("/api/v1/eval/roc-curve-plot")
def roc_curve_plot():
    """Debugging endpoint mirroring the ROC curve plot from analysis.ipynb,
    computed on the held-out test split. Not called by the Java backend."""
    if X_test is None or y_test is None:
        raise HTTPException(status_code=404, detail="No test data persisted in kyc_train_data.pkl")

    y_proba = pipeline.predict_proba(X_test)[:, 1]
    fpr, tpr, _ = roc_curve(y_test, y_proba)
    roc_auc = roc_auc_score(y_test, y_proba)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(fpr, tpr, color="darkorange", lw=2, label=f"ROC (AUC = {roc_auc:.3f})")
    ax.plot([0, 1], [0, 1], color="navy", linestyle="--")
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curve")
    ax.legend(loc="lower right")
    fig.tight_layout()
    return {"roc_curve_plot": plot_to_base64(fig)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)