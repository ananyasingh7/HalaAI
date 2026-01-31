import re

_THINK_BLOCK = re.compile(r"<think>.*?</think>\n*", flags=re.DOTALL | re.IGNORECASE)
_THINK_TRAILING = re.compile(r"<think>.*$", flags=re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    if not text:
        return text
    cleaned = _THINK_BLOCK.sub("", text)
    cleaned = _THINK_TRAILING.sub("", cleaned)
    return cleaned
