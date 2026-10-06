import re


def sanitize_for_speech(text):
    text = re.sub(r"```(?:[^\n]*)\n?|```", " ", text)
    text = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}(?:[-+*]|\d+[.)])\s+", "", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"[*_~`]", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()
