"""Custom template filters for schedule views."""

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key."""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def make_list(number):
    """Convert number to list of that length (for range iteration)."""
    try:
        return list(range(int(number)))
    except (ValueError, TypeError):
        return []
