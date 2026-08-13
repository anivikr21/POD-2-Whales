# LipidLens

LipidLens is a Vercel-ready XGBoost variant-classification application. The
browser uploads a ClinVar-style CSV to a same-origin FastAPI endpoint, which
performs feature engineering and server-side inference.

The model predicts one of three variant classes:

- `Benign`
- `Pathogenic`
- `Uncertain/Conflicting`

This output is decision support, not a patient diagnosis.

## Project structure

```text
api/index.py       FastAPI health and prediction endpoints
models/            Exported XGBoost model assets
public/            Static HTML, CSS, and browser JavaScript
requirements.txt   Python runtime dependencies
vercel.json         Vercel function configuration
```

## Add the trained model

Run this after the XGBoost training cell in Colab:

```python
import json
from google.colab import files

model.save_model("xgboost_model.json")
with open("model_metadata.json", "w") as metadata_file:
    json.dump({
        "classes": le.classes_.tolist(),
    }, metadata_file)

files.download("xgboost_model.json")
files.download("model_metadata.json")
```

Place the downloaded files in `models/` using those exact filenames. Do not
commit training data, patient records, API keys, or Colab secrets.

## Run locally

Install Vercel CLI 48.1.8 or later, then run:

```powershell
npm install --global vercel
vercel dev
```

Open `http://localhost:3000`. Check the backend directly at
`http://localhost:3000/api/health`.

## Deploy

1. Push this repository to GitHub.
2. In Vercel, select **Add New → Project**.
3. Import the `POD-2-Whales` repository.
4. Leave the framework and build settings at their detected defaults.
5. Select **Deploy**.

The frontend and API use the same Vercel domain, so no ngrok URL, Colab runtime,
CORS configuration, or frontend secret is required.

## Input requirements

Uploads must be CSV files no larger than 4 MB and contain these columns:

- `Type`
- `Genes`
- `Condition`
- `Type`

Vercel rejects function request bodies above 4.5 MB; the application uses a
4 MB file limit to leave room for multipart request metadata.

The backend uses the CPU-only XGBoost distribution. It reads the same model
format as standard XGBoost while avoiding GPU and federated-learning binaries
that would exceed Vercel's 500 MB function bundle limit.
