import base64
import io
import os
from typing import List, Optional

import dice_ml
import joblib
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for server rendering
import matplotlib.pyplot as plt
import pandas as pd
import shap
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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
    client_type: str
    nationality: str
    jurisdiction_risk: str
    age: int
    annual_income_band: str
    main_source_of_funds: str
    is_pep: int
    adverse_media_hits: int
    is_cross_border: int
    product_type: str
    total_docs_submitted: int
    verified_docs_count: int
    expired_docs_count: int
    has_unverified_docs: int


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
    row = features.dict()
    row["annual_income_band_encoded"] = INCOME_MAP.get(row.pop("annual_income_band"), 0)
    row["jurisdiction_risk_encoded"] = RISK_MAP.get(row.pop("jurisdiction_risk"), 0)
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
        cf = _dice_explainer.generate_counterfactuals(
            df_raw,
            total_CFs=3,
            desired_class=1,
            features_to_vary=ACTIONABLE_FEATURES,
        )
        cf_df = cf.cf_examples_list[0].final_cfs_df
        if cf_df is None or cf_df.empty:
            return None
        original = df_raw.iloc[0]
        best = cf_df.iloc[0]
        recommendations = [
            Recommendation(feature=col, current_value=str(original[col]), suggested_value=str(best[col]))
            for col in ACTIONABLE_FEATURES
            if col in best and str(best[col]) != str(original[col])
        ]
        return recommendations or None
    except Exception:
        # DiCE can fail to find a feasible counterfactual (e.g. already at the
        # limit of actionable fields) - treat as "no recommendation available".
        return None


@app.get("/health")
def health():
    return {"status": "ok"}


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)