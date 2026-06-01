import re


def clean_project_name(name):
    """Best-effort cleanup of a listing-page project name.

    Handles common artifacts like trailing tickers in parentheses and exact
    doubled strings (e.g. 'USDSUSDS' -> 'USDS'). The enrichment step refines
    this further from the project page's title when available.
    """
    if not name:
        return ""

    name = str(name).strip()

    # Drop a trailing "(TICKER)".
    name = re.sub(r"\s*\([A-Za-z0-9]{2,12}\)\s*$", "", name)

    # Strip an appended all-caps ticker glued to the name
    # (Wrapped BitcoinWBTC -> Wrapped Bitcoin). Requires a lowercase letter
    # right before the run so we don't mangle genuinely all-caps names.
    name = re.sub(r"(?<=[a-z])[A-Z][A-Z0-9]{1,5}$", "", name).strip()

    # Collapse an exactly-doubled string (USDSUSDS -> USDS).
    if len(name) >= 4 and len(name) % 2 == 0:
        half = len(name) // 2
        if name[:half] == name[half:]:
            name = name[:half]

    name = re.sub(r"\s+", " ", name).strip()
    return name
