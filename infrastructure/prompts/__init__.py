"""Prompts module for MongoDB-backed prompt management."""
from .prompt_service import (
    get_system_prompt,
    get_user_template,
    get_system_prompt_cached,
    get_user_template_cached,
    refresh_cache,
)

__all__ = [
    "get_system_prompt",
    "get_user_template",
    "get_system_prompt_cached",
    "get_user_template_cached",
    "refresh_cache",
]
