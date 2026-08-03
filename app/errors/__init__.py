"""Public error-handling API."""

from app.errors.classify import ErrorKind, classify_error, locale_key_for_error, log_handled_error
from app.errors.notify import notify_user_of_error, resolve_i18n, safe_user_error_text

__all__ = [
    "ErrorKind",
    "classify_error",
    "locale_key_for_error",
    "log_handled_error",
    "notify_user_of_error",
    "resolve_i18n",
    "safe_user_error_text",
]
