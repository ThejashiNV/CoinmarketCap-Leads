import os

import pandas as pd


# Canonical output schema — every column here appears in the CSV/XLSX export.
# Order matches the frontend Results table.
COLUMNS = [
    "Company / Project Name",
    "Official Website URL",
    "Official Email IDs",
    "Contact Page URL",
    "LinkedIn URLs",
    "GitHub URLs",
    "Twitter/X URLs",
    "Telegram URLs",
    "Discord URLs",
    "Founder Name",
    "Founder LinkedIn",
    "Industry / Category",
    "Short Description",
    "Source Platform",
    "Discovery URL",
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
    df = df.drop_duplicates(subset=["Discovery URL"], keep="first")

    df.to_csv(csv_path, index=False)
    try:
        df.to_excel(xlsx_path, index=False)
    except Exception:
        # XLSX is a convenience export; never fail the run over it.
        pass

    return df
