from django import template

register = template.Library()

@register.filter
def bold_before_colon(text):
    """Bold everything before the first colon in text."""
    if ':' in text:
        parts = text.split(':', 1)
        return f'<strong>{parts[0]}:</strong>{parts[1]}'
    return text
