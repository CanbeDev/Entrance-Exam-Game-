"""Allowlisted projections only; these helpers never load or mutate a database."""
from collections.abc import Iterable, Mapping
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from app.models.events import ActionResult
from app.models.game_api import PublicActionResult, PublicEventPage, PublicGame
from app.services.game_action_service import ActionReceipt


def public_game(document: Mapping) -> dict:
    data = dict(document)
    if "_id" in data:
        data["_id"] = str(data["_id"])
    return PublicGame.model_validate(data).model_dump(mode="json", by_alias=True, exclude_unset=True)


def public_result(result: ActionResult) -> dict:
    # The caller must supply the committed/replayed service result, never a
    # prepared NPC proposal. Nested public schemas discard persistence metadata.
    return PublicActionResult.model_validate(result.model_dump()).model_dump(
        mode="json", by_alias=True, exclude_unset=True)


def _known_fields(annotation, value):
    """Discard future private metadata before canonical receipt validation.

    The canonical model still rejects malformed required gameplay fields. This
    traversal follows declared model fields rather than accepting arbitrary
    nested dictionaries from persistence into the public contract.
    """
    if isinstance(value, BaseModel):
        value = value.model_dump()
    origin, arguments = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        return _known_fields(arguments[0], value)
    if origin in (Union, UnionType):
        if value is None:
            return None
        models = [item for item in arguments if isinstance(item, type) and issubclass(item, BaseModel)]
        if len(models) == 1:
            return _known_fields(models[0], value)
        if isinstance(value, Mapping):
            for model in models:
                for name, field in model.model_fields.items():
                    if get_origin(field.annotation) is Literal and value.get(name) in get_args(field.annotation):
                        return _known_fields(model, value)
        return value  # Canonical validation rejects unknown discriminators.
    if isinstance(annotation, type) and issubclass(annotation, BaseModel) and isinstance(value, Mapping):
        return {name: _known_fields(field.annotation, value[name])
                for name, field in annotation.model_fields.items() if name in value}
    if origin in (tuple, list) and isinstance(value, (tuple, list)):
        element_type = arguments[0] if arguments else object
        return [_known_fields(element_type, item) for item in value]
    return value


def _receipt(value: ActionReceipt | Mapping) -> ActionReceipt:
    if isinstance(value, ActionReceipt):
        data = value.model_dump()
    elif isinstance(value, Mapping):
        # _id and future receipt metadata are not part of the durable result.
        data = value
    else:
        raise ValueError("Invalid persisted receipt")
    receipt = ActionReceipt.model_validate(_known_fields(ActionReceipt, data))
    if receipt.result.state.revision != receipt.command.expected_revision + 1:
        raise ValueError("Invalid committed receipt revision")
    return receipt


def public_event_page(receipts: Iterable[ActionReceipt | Mapping], after_revision: int = 0,
                      limit: int = 50) -> dict:
    """Project already persisted receipts from one game, ordered by revision.

    The repository should supply at most limit+1 rows so has_more is accurate.
    Missing NPC evidence on historical receipts is supported by ActionResult.
    No receipt fingerprint, ownership, cookie, digest or tie-break seed is public.
    """
    if type(after_revision) is not int or after_revision < 0:
        raise ValueError("after_revision must be a non-negative integer")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    parsed = [_receipt(receipt) for receipt in receipts]
    if len({receipt.game_id for receipt in parsed}) > 1:
        raise ValueError("Receipts must belong to one game")
    ordered = sorted((receipt for receipt in parsed if receipt.result.state.revision > after_revision),
                     key=lambda receipt: receipt.result.state.revision)
    if len({receipt.result.state.revision for receipt in ordered}) != len(ordered):
        raise ValueError("Duplicate committed revision")
    entries = []
    for receipt in ordered[:limit]:
        result = public_result(receipt.result)
        entries.append({
            "revision": receipt.result.state.revision,
            "action_id": receipt.command.action_id,
            "actor": receipt.actor.model_dump(),
            "committed_at": receipt.result.state.updated_at,
            "events": result["events"],
            "npc_decision": result["npc_decision"],
        })
    page = PublicEventPage(events=entries, after_revision=after_revision,
                           next_after_revision=entries[-1]["revision"] if entries else after_revision,
                           has_more=len(ordered) > limit)
    return page.model_dump(mode="json")
