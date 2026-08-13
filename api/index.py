from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
import json
import re

import numpy as np
import pandas as pd
import xgboost as xgb
from fastapi import FastAPI, File, HTTPException, UploadFile


APP_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = APP_ROOT / "models"
MODEL_PATH = MODEL_DIR / "xgboost_model.json"
METADATA_PATH = MODEL_DIR / "model_metadata.json"

# Vercel Functions reject request payloads above 4.5 MB. Keeping the CSV at
# 4 MB leaves room for the multipart request wrapper.
MAX_UPLOAD_BYTES = 4 * 1024 * 1024
MAX_ROWS = 25_000

RAW_REQUIRED_COLUMNS = (
    "Type",
    "Variation",
    "Molecular consequence",
    "Protein change",
    "GRCh38 Location",
    "Review status",
)

FEATURE_COLUMNS = (
    "is_snv",
    "is_deletion",
    "is_duplication",
    "is_indel",
    "is_cnv",
    "has_missense",
    "has_nonsense",
    "has_frameshift",
    "has_splice",
    "has_utr",
    "has_intron",
    "has_synonymous",
    "has_protein_change",
    "pos_grch38",
    "review_strength",
)

app = FastAPI(
    title="LipidLens XGBoost API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


def missing_model_files() -> list[str]:
    return [
        path.name
        for path in (MODEL_PATH, METADATA_PATH)
        if not path.is_file()
    ]


@lru_cache(maxsize=1)
def load_model_bundle():
    missing = missing_model_files()
    if missing:
        raise FileNotFoundError(
            "Missing model assets: " + ", ".join(missing)
        )

    model = xgb.XGBClassifier()
    model.load_model(MODEL_PATH)
    with METADATA_PATH.open(encoding="utf-8") as metadata_file:
        metadata = json.load(metadata_file)

    class_names = [str(name) for name in metadata["classes"]]
    position_median = float(metadata["training_position_median"])
    if len(class_names) != model.n_classes_:
        raise ValueError("Model metadata class count does not match the XGBoost model.")
    return model, class_names, position_median


def extract_position(location: object) -> float:
    if pd.isna(location):
        return np.nan
    match = re.search(r":(\d+)", str(location))
    return float(match.group(1)) if match else np.nan


def review_strength(status: object) -> int:
    normalized = str(status).lower()
    if "expert panel" in normalized:
        return 3
    if "multiple submitters" in normalized:
        return 2
    if "single submitter" in normalized:
        return 1
    return 0


def prepare_features(raw_df: pd.DataFrame, position_median: float) -> pd.DataFrame:
    missing = [column for column in RAW_REQUIRED_COLUMNS if column not in raw_df.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))

    data = raw_df.copy()
    data = data.dropna(subset=["Type", "Variation"]).reset_index(drop=True)
    if data.empty:
        raise ValueError("No usable rows remain after validating Type and Variation.")
    if len(data) > MAX_ROWS:
        raise ValueError(f"The CSV contains more than {MAX_ROWS:,} usable rows.")

    data["is_snv"] = (data["Type"] == "single nucleotide variant").astype(int)
    data["is_deletion"] = (data["Type"] == "Deletion").astype(int)
    data["is_duplication"] = (data["Type"] == "Duplication").astype(int)
    data["is_indel"] = data["Type"].isin(["Indel", "Insertion"]).astype(int)
    data["is_cnv"] = data["Type"].str.contains(
        "copy number|Haplotype|Inversion", case=False, na=False
    ).astype(int)

    consequence = data["Molecular consequence"]
    data["has_missense"] = consequence.str.contains(
        "missense", case=False, na=False
    ).astype(int)
    data["has_nonsense"] = consequence.str.contains(
        "nonsense|stop", case=False, na=False
    ).astype(int)
    data["has_frameshift"] = consequence.str.contains(
        "frameshift", case=False, na=False
    ).astype(int)
    data["has_splice"] = consequence.str.contains(
        "splice", case=False, na=False
    ).astype(int)
    data["has_utr"] = consequence.str.contains(
        "utr|5 prime|3 prime", case=False, na=False
    ).astype(int)
    data["has_intron"] = consequence.str.contains(
        "intron", case=False, na=False
    ).astype(int)
    data["has_synonymous"] = consequence.str.contains(
        "synonymous", case=False, na=False
    ).astype(int)
    data["has_protein_change"] = data["Protein change"].notna().astype(int)
    data["pos_grch38"] = (
        data["GRCh38 Location"].apply(extract_position).fillna(position_median)
    )
    data["review_strength"] = data["Review status"].apply(review_strength)

    return data.loc[:, FEATURE_COLUMNS]


@app.get("/api/health")
def health():
    missing = missing_model_files()
    return {
        "status": "ready" if not missing else "configuration_required",
        "model": "XGBoost",
        "missing_model_files": missing,
    }


@app.post("/api/predict")
async def predict(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The CSV exceeds the 4 MB upload limit.",
        )

    try:
        raw_df = pd.read_csv(BytesIO(contents), low_memory=False)
    except Exception as error:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid CSV.") from error

    try:
        model, class_names, position_median = load_model_bundle()
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    try:
        features = prepare_features(raw_df, position_median)
        encoded_predictions = model.predict(features).astype(int)
        probability_rows = model.predict_proba(features)
        labels = [class_names[index] for index in encoded_predictions]
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail="Model inference failed.") from error

    summary = {name: 0 for name in class_names}
    for label in labels:
        summary[str(label)] = summary.get(str(label), 0) + 1

    first_probabilities = {
        class_name: float(probability)
        for class_name, probability in zip(class_names, probability_rows[0])
    }

    return {
        "rows_analyzed": len(labels),
        "model": "XGBoost",
        "summary": summary,
        "first_result": {
            "classification": str(labels[0]),
            "confidence": float(max(probability_rows[0])),
            "probabilities": first_probabilities,
        },
    }
