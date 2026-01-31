import re

YEAR_PATTERN = re.compile(r"\b20\d{2}\b")

PROBE_KEYWORDS = (
    "today",
    "latest",
    "current",
    "now",
    "recent",
    "breaking",
    "live",
    "news",
    "score",
    "scores",
    "standings",
    "schedule",
    "price",
    "stock",
    "market",
    "forecast",
    "weather",
    "earnings",
    "release",
    "updated",
    "update",
    "yesterday",
    "tomorrow",
    "this week",
    "this month",
    "this year",
)


def should_probe_search(prompt: str) -> bool:
    if not prompt:
        return False
    text = prompt.lower()
    if "[search:" in text:
        return True
    if "search for" in text or "look up" in text or "browse" in text:
        return True
    if YEAR_PATTERN.search(text):
        return True
    return any(keyword in text for keyword in PROBE_KEYWORDS)
