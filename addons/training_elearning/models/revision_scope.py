"""A server-only, request-local scope for native file updates during audited edits."""

from contextlib import contextmanager
from contextvars import ContextVar
import hashlib

_SCOPE = ContextVar("learning_editorial_scope", default=None)


@contextmanager
def lesson_revision(slide):
    token = _SCOPE.set((slide.env.uid, slide.id))
    try:
        yield
    finally:
        _SCOPE.reset(token)


def editing_lesson(slide):
    return len(slide) == 1 and _SCOPE.get() == (slide.env.uid, slide.id)


def digest_fields(record, names):
    result = {}
    for name in names:
        value = record[name]
        content = value.content if hasattr(value, "content") else (value or "").encode()
        result[name] = hashlib.sha256(content).hexdigest()
    return result
