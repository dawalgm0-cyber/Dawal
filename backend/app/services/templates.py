"""Render message_templates by key with {placeholder} substitution. Missing
placeholders are left intact rather than raising, so a template edit that adds a
placeholder never crashes a live flow."""

from sqlalchemy.orm import Session

from app.models import MessageTemplate


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


class TemplateNotFound(KeyError):
    pass


def render(db: Session, key: str, **values) -> str:
    row = db.query(MessageTemplate).filter_by(key=key).one_or_none()
    if row is None:
        raise TemplateNotFound(f"message_template not found: {key}")
    return row.template_text.format_map(_SafeDict(**values))
