import logging
import os
import time

import pandas as pd

logger = logging.getLogger("scraper")


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

    _safe_write(df, csv_path, "csv")
    _safe_write(df, xlsx_path, "xlsx")

    return df


def _safe_write(df, path, kind):
    """Write CSV/XLSX without ever crashing the run.

    On Windows the target file is commonly locked (e.g. open in Excel), which
    raises PermissionError. Rather than discard a completed run's results, fall
    back to a timestamped sibling file and log where it landed.
    """
    writer = df.to_csv if kind == "csv" else df.to_excel
    try:
        writer(path, index=False)
        return path
    except Exception as exc:
        base, ext = os.path.splitext(path)
        fallback = f"{base}_{time.strftime('%Y%m%d_%H%M%S')}{ext}"
        logger.warning("export to %s failed (%s); writing fallback %s", path, exc, fallback)
        try:
            writer(fallback, index=False)
            return fallback
        except Exception as exc2:
            logger.error("fallback export to %s also failed: %s", fallback, exc2)
            return ""
