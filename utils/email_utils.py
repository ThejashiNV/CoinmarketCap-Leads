import re


def is_valid_email(email):
    """
    Basic email validation.
    """
    if not email:
        return False

    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    return re.match(pattern, email.strip()) is not None


def select_best_email(emails):
    """
    Select the best business email from a list.

    Priority:
    business@ > contact@ > info@ > hello@ > support@ > any valid email
    """
    if not emails:
        return ""

    # Clean and validate
    cleaned = []
    seen = set()

    for email in emails:
        if not email:
            continue

        email = email.strip().lower()

        if not is_valid_email(email):
            continue

        if email not in seen:
            cleaned.append(email)
            seen.add(email)

    if not cleaned:
        return ""

    priority_prefixes = [
        "business@",
        "contact@",
        "info@",
        "hello@",
        "support@",
    ]

    # Return first match based on priority
    for prefix in priority_prefixes:
        for email in cleaned:
            if email.startswith(prefix):
                return email

    # Otherwise return the first valid email
    return cleaned[0]