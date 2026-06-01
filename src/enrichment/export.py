import os

import pandas as pd


# Canonical output schema — kept stable so the frontend/exports never drift.
COLUMNS = [
    "Project Name",
    "Platform",
    "Source URL",
    "Project Page URL",
    "Official Website URL",
    "Official Email ID",
    "Email Source",
    "Email Confidence",
    "LinkedIn URLs",
    "Telegram URLs",
    "Twitter URLs",
    "Discord URLs",
    "Github URLs",
    "Missing Fields",
]


def export_leads(rows, csv_path, xlsx_path):
    """Write cleaned, de-duplicated leads to CSV and XLSX with a stable schema."""
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)

    df = pd.DataFrame(rows)

    # Guarantee every column exists and is ordered, even for empty runs.
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = "N/A"
    df = df[COLUMNS]

    df = df.fillna("N/A")
    df = df.drop_duplicates(subset=["Project Page URL"], keep="first")

    df.to_csv(csv_path, index=False)
    try:
        df.to_excel(xlsx_path, index=False)
    except Exception:
        # XLSX is a convenience export; never fail the run over it.
        pass

    return df
