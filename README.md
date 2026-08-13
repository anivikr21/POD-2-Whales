# POD-2-Whales

This is the repo that we will be using to collaborate on the code for this project.
# POD 2 : Whales — LipidLens

A lightweight UI for uploading structured clinical data to screen for familial hypercholesterolemia (FH).

The interface validates CSV file type and a 10 MB size limit, sends the file to the team's model API, and displays the XGBoost variant classifications.

## Run with the Colab XGBoost model

1. Open the `POD 2` Colab notebook.
2. Run the XGBoost training cell and choose the ClinVar training CSV when prompted.
3. Add an ngrok token to Colab Secrets as `NGROK_AUTHTOKEN` and enable notebook access.
4. Run the final `XGBoost prediction API for the LipidLens frontend` cell.
5. Copy the printed **Backend URL**.
6. From this directory, run `py -m http.server 5500` and open `http://localhost:5500`.
7. Upload a prediction CSV, click **Analyze data**, and paste the Backend URL when prompted.

The browser remembers the Backend URL. If Colab restarts, clear the browser key
`lipidlensBackendUrl` or use a private window so the site asks for the new URL.

The XGBoost model classifies variants as `Benign`, `Pathogenic`, or
`Uncertain/Conflicting`; it does not produce an individual patient's probability of FH.
