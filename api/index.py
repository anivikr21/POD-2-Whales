from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
import json

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
    "Genes",
    "Condition",
    "Type",
)

TYPE_FEATURES = (
    "is_snv",
    "is_deletion",
    "is_duplication",
    "is_indel",
    "is_cnv",
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

    model = xgb.Booster()
    model.load_model(str(MODEL_PATH))
    with METADATA_PATH.open(encoding="utf-8") as metadata_file:
        metadata = json.load(metadata_file)

    class_names = [str(name) for name in metadata["classes"]]
    model_feature_names = model.feature_names
    if not model_feature_names:
        raise ValueError("The XGBoost model does not contain feature names.")
    if len(model_feature_names) != model.num_features():
        raise ValueError("Model feature metadata is inconsistent.")
    return model, class_names, model_feature_names


def prepare_features(
    raw_df: pd.DataFrame, model_feature_names: list[str]
) -> pd.DataFrame:
    missing = [column for column in RAW_REQUIRED_COLUMNS if column not in raw_df.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))

    data = raw_df.copy()
    data = data.dropna(subset=["Type"]).reset_index(drop=True)
    if data.empty:
        raise ValueError("No usable rows remain after validating Type.")
    if len(data) > MAX_ROWS:
        raise ValueError(f"The CSV contains more than {MAX_ROWS:,} usable rows.")

    supported_features = set(TYPE_FEATURES)
    supported_features.update(
        feature
        for feature in model_feature_names
        if feature.startswith("Genes_") or feature.startswith("Condition_")
    )
    unexpected = [
        feature for feature in model_feature_names if feature not in supported_features
    ]
    if unexpected:
        raise ValueError(
            "Unsupported model feature schema: " + ", ".join(unexpected[:5])
        )

    features = pd.DataFrame(
        np.zeros((len(data), len(model_feature_names)), dtype=np.float32),
        columns=model_feature_names,
    )

    genes = data["Genes"].fillna("").astype(str)
    conditions = data["Condition"].fillna("").astype(str)
    for row_index, (gene, condition) in enumerate(zip(genes, conditions)):
        gene_column = f"Genes_{gene}"
        condition_column = f"Condition_{condition}"
        if gene_column in features.columns:
            features.at[row_index, gene_column] = 1
        if condition_column in features.columns:
            features.at[row_index, condition_column] = 1

    features["is_snv"] = (data["Type"] == "single nucleotide variant").astype(int)
    features["is_deletion"] = (data["Type"] == "Deletion").astype(int)
    features["is_duplication"] = (data["Type"] == "Duplication").astype(int)
    features["is_indel"] = data["Type"].isin(["Indel", "Insertion"]).astype(int)
    features["is_cnv"] = data["Type"].str.contains(
        "copy number|Haplotype|Inversion", case=False, na=False
    ).astype(int)

    return features


@app.get("/api/health")
def health():
    missing = missing_model_files()
    if missing:
        return {
            "status": "configuration_required",
            "model": "XGBoost",
            "missing_model_files": missing,
        }

    try:
        load_model_bundle()
    except Exception as error:
        return {
            "status": "configuration_required",
            "model": "XGBoost",
            "missing_model_files": [],
            "detail": str(error),
        }

    return {
        "status": "ready",
        "model": "XGBoost",
        "missing_model_files": [],
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
        model, class_names, model_feature_names = load_model_bundle()
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    try:
        features = prepare_features(raw_df, model_feature_names)
        feature_matrix = xgb.DMatrix(features, feature_names=model_feature_names)
        prediction_options = {}
        best_iteration = model.attr("best_iteration")
        if best_iteration is not None:
            prediction_options["iteration_range"] = (0, int(best_iteration) + 1)

        probability_rows = model.predict(feature_matrix, **prediction_options)
        if probability_rows.ndim != 2 or probability_rows.shape[1] != len(class_names):
            raise ValueError("Model output does not match the configured classes.")

        encoded_predictions = np.argmax(probability_rows, axis=1).astype(int)
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
