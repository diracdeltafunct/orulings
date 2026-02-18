import os
import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Build a mapping of lowercase keyword -> actual filename on disk
_IMAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
_KEYWORD_TO_FILE = {}
if os.path.isdir(_IMAGE_DIR):
    for fname in os.listdir(_IMAGE_DIR):
        if fname.lower().endswith(".webp"):
            keyword = fname[:-5]  # strip .webp
            _KEYWORD_TO_FILE[keyword.lower()] = fname


# Mapping for :rb_*: tokens to image files
_RB_TOKEN_MAP = {
    "rb_rune_rainbow": "rune.webp",
    "rb_rune_calm": "calm.webp",
    "rb_rune_fury": "fury.webp",
    "rb_rune_mind": "mind.webp",
    "rb_rune_body": "body.webp",
    "rb_rune_chaos": "chaos.webp",
    "rb_rune_order": "order.webp",
    "rb_might": "might.webp",
    "rb_exhaust": "exhaust.webp",
}
# Add energy mappings: rb_energy_0 -> 0.svg, rb_energy_1 -> 1.svg, etc.
for i in range(13):
    _RB_TOKEN_MAP[f"rb_energy_{i}"] = f"{i}.svg"


def _replace_rb_token(match):
    token = match.group(1)
    fname = _RB_TOKEN_MAP.get(token)
    if fname:
        return (
            f'<img src="/static/{fname}" '
            f'alt="{token}" '
            f'title="{token}" '
            f'class="keyword-icon" '
            f'style="height: 1.2em; vertical-align: middle;">'
        )
    return match.group(0)


def _replace_keyword(match):
    keyword = match.group(1)
    # Try exact match first, then uppercase, then base keyword (strip trailing numbers)
    lookup = keyword.lower()
    fname = _KEYWORD_TO_FILE.get(lookup)

    if not fname:
        # Try base keyword without trailing number, e.g. "Shield 3" -> "SHIELD 3"
        # or "Assault 2" -> "ASSAULT 2"
        base = re.sub(r"\s*\d+$", "", lookup)
        fname = _KEYWORD_TO_FILE.get(base)

    if fname:
        escaped_fname = fname.replace(" ", "%20")
        return (
            f'<img src="/static/{escaped_fname}" '
            f'alt="{keyword}" '
            f'title="{keyword}" '
            f'class="keyword-icon" '
            f'style="height: 1.2em; vertical-align: middle;">'
        )
    return match.group(0)


@register.filter(name="replace_keywords")
def replace_keywords(text):
    """Replace [Keyword] and :rb_*: patterns in card text with corresponding images."""
    if not text:
        return text
    result = str(text)
    result = re.sub(r"\[([^\]]+)\]", _replace_keyword, result)
    result = re.sub(r":(\w+):", _replace_rb_token, result)
    return mark_safe(result)
