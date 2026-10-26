"""Offline BSON schema manifest. No settings, clients or database side effects.

These are structural storage checks; cross-field game rules remain in the engine.
Pydantic defaults stay optional for historical documents. No migration is implied.
"""
from copy import deepcopy

from app.models.game import Game, InitializedGame
from app.models.game_access import GameAccess
from app.models.runtime_game import RuntimeGame
from app.services.game_action_service import ActionReceipt


# Persisted Pydantic ISO strings: date-only snapshots and timestamps with optional
# fractions/UTC offsets (including historical naive timestamps). Calendar/engine
# semantics remain application checks; BSON dates remain independently accepted.
_ISO_DATE = r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
_ISO_TIME = (r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
             r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])?")


def _model_schema(model):
    source = model.model_json_schema()
    definitions = source.get("$defs", {})

    def convert(node):
        if "$ref" in node:
            return convert(definitions[node["$ref"].split("/")[-1]])
        result = {}
        for key, value in node.items():
            if key in {"title", "description", "default", "$defs", "discriminator"}:
                continue
            if key == "format":
                if value in {"date", "date-time"}:
                    continue  # handled with type, independently of key order
                else:
                    raise ValueError("Unsupported schema format")
            elif key == "type":
                # format can precede type in Pydantic output.
                if node.get("format") in {"date", "date-time"}:
                    suffix = "" if node["format"] == "date" else "[Tt ]" + _ISO_TIME
                    result["anyOf"] = [{"bsonType": "date"},
                        # Strict end assertion also rejects a trailing newline.
                        {"bsonType": "string", "pattern": "^" + _ISO_DATE + suffix + r"(?![\s\S])"}]
                else:
                    result["bsonType"] = {"integer": ["int", "long"],
                        "number": ["int", "long", "double", "decimal"],
                        "boolean": "bool"}.get(value, value)
            elif key == "const":
                result["enum"] = [value]
            elif key in {"exclusiveMinimum", "exclusiveMaximum"}:
                bound = "minimum" if key == "exclusiveMinimum" else "maximum"
                result[bound], result[key] = value, True
            elif key == "properties":
                result[key] = {name: convert(child) for name, child in value.items()}
            elif key in {"anyOf", "oneOf", "allOf"}:
                result[key] = [convert(child) for child in value]
            elif key == "items":
                result[key] = convert(value)
            elif key == "prefixItems":
                result["items"] = [convert(child) for child in value]
                result["additionalItems"] = False
            elif key in {"required", "enum", "minimum", "maximum", "minLength", "maxLength",
                         "pattern", "minItems", "maxItems", "additionalProperties"}:
                result[key] = value
            else:
                raise ValueError(f"Unsupported schema keyword: {key}")
        return result

    return convert(source)


def _object(properties, required=None):
    return {"bsonType": "object", "properties": properties,
            "required": list(properties) if required is None else required}


def mongo_validators():
    """Fresh manifests: unversioned legacy, v2 setup, v3 runtime and old receipts."""
    identifier = {"bsonType": "string", "minLength": 1}
    integer = {"bsonType": ["int", "long"], "minimum": 0}
    date = {"bsonType": "date"}  # TTL/auth operations require BSON dates.
    games = []
    for model in (Game, InitializedGame, RuntimeGame):
        schema = _model_schema(model)
        schema["properties"]["_id"] = {"bsonType": "objectId"}
        schema["properties"]["access"] = _model_schema(GameAccess)
        schema["properties"]["creation"] = _object({"key": identifier, "fingerprint": identifier})
        if model is Game:
            schema["not"] = {"required": ["schema_version"]}
        else:
            schema["required"] = list(dict.fromkeys([*schema.get("required", []), "schema_version"]))
        games.append(schema)
    receipt = _model_schema(ActionReceipt)
    receipt["properties"]["_id"] = identifier
    users = _object({"_id": {"bsonType": "objectId"}, "username": identifier,
        "username_key": identifier, "password_hash": identifier,
        "status": {"enum": ["active", "disabled"]},
        "auth_version": {**integer, "minimum": 1}, "authorization_revision": integer,
        "created_at": date}, ["username", "username_key", "password_hash", "status", "auth_version", "created_at"])
    sessions = _object({"_id": {"bsonType": "string", "pattern": "^[0-9a-f]{64}$"},
        "user_id": identifier, "auth_version": {**integer, "minimum": 1}, "csrf_token": identifier,
        "created_at": date, "last_seen_at": date, "expires_at": date,
        "revoked_at": {"bsonType": ["date", "null"]}, "revision": integer})
    limits = _object({"_id": {"bsonType": "string", "pattern": "^[0-9a-f]{64}$"},
        "count": {**integer, "minimum": 1}, "expires_at": date})
    return deepcopy({name: {"$jsonSchema": schema} for name, schema in {
        "games": {"oneOf": games}, "users": users, "auth_sessions": sessions,
        "auth_rate_limits": limits, "game_action_receipts": receipt}.items()})
