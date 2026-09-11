"""Keyset pagination after permission filtering, with validated scoped cursors."""

import base64
import binascii
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from services.policy_service import PolicyError
from sqlalchemy import Select, and_, or_
from sqlalchemy.orm import Session


def paginate(
    db: Session, query: Select, model: Any, limit: int, cursor: str | None, scope: str
) -> dict:
    if cursor:
        try:
            value = json.loads(
                base64.b64decode(cursor.encode(), altchars=b"-_", validate=True)
            )
            if (
                not isinstance(value, dict)
                or set(value) != {"at", "id", "scope"}
                or not all(isinstance(item, str) for item in value.values())
                or value["scope"] != scope
            ):
                raise ValueError
            at = datetime.fromisoformat(value["at"])
            identifier = UUID(value["id"])
            if at.tzinfo is None:
                raise ValueError
        except (ValueError, TypeError, KeyError, binascii.Error, UnicodeError):
            raise PolicyError(
                422, "invalid_cursor", "Invalid pagination cursor"
            ) from None
        query = query.where(
            or_(
                model.created_at > at,
                and_(model.created_at == at, model.id > identifier),
            )
        )
    rows = list(db.scalars(query.order_by(model.created_at, model.id).limit(limit + 1)))
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        at = last.created_at.replace(tzinfo=last.created_at.tzinfo or timezone.utc)
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(
                {"at": at.isoformat(), "id": str(last.id), "scope": scope}
            ).encode()
        ).decode()
    return {"items": rows[:limit], "next_cursor": next_cursor}
