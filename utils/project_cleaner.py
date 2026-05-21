import re


def clean_project_name(name):
    """
    Clean extracted crypto project names.

    Examples:
    - Wrapped Bitcoin (WBTC) -> Wrapped Bitcoin
    - Chainlink (LINK) -> Chainlink
    - USDSUSDS -> USDS
    """

    if not name:
        return ""

    name = str(name).strip()

    # Remove ticker symbols in parentheses
    name = re.sub(r"\s*\([A-Z0-9]{2,10}\)\s*$", "", name)

    # Remove duplicate repeated uppercase words (USDSUSDS -> USDS)
    if len(name) % 2 == 0:
        half = len(name) // 2
        if name[:half] == name[half:]:
            name = name[:half]

    # Remove extra whitespace
    name = re.sub(r"\s+", " ", name).strip()

    return name