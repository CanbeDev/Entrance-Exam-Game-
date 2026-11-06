"""Optional-only manifests. Never merge these into core gameplay readiness."""
from copy import deepcopy

JOB_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "additionalProperties": False,
        "required": [
            "_id",
            "schema_version",
            "game_id",
            "revision",
            "action_id",
            "status",
            "created_at",
            "updated_at",
            "available_at",
            "lease_token",
            "lease_expires_at",
            "attempts",
            "max_attempts",
            "last_error",
            "failure_reason",
            "completed_at"
        ],
        "properties": {
            "_id": {
                "bsonType": "objectId"
            },
            "schema_version": {
                "bsonType": [
                    "int",
                    "long"
                ],
                "enum": [
                    1
                ]
            },
            "game_id": {
                "bsonType": "string",
                "pattern": "^[0-9a-f]{24}$"
            },
            "revision": {
                "bsonType": [
                    "int",
                    "long"
                ],
                "minimum": 1
            },
            "action_id": {
                "bsonType": "string",
                "minLength": 1,
                "maxLength": 128,
                "pattern": "^[a-zA-Z0-9_-]+$"
            },
            "status": {
                "bsonType": "string",
                "enum": [
                    "queued",
                    "claimed",
                    "ready",
                    "failed"
                ]
            },
            "created_at": {
                "bsonType": "date"
            },
            "updated_at": {
                "bsonType": "date"
            },
            "available_at": {
                "bsonType": "date"
            },
            "lease_token": {
                "bsonType": [
                    "string",
                "null"
                ],
                "pattern": "^[A-Za-z0-9_-]{16,128}$"
            },
            "lease_expires_at": {
                "bsonType": [
                    "date",
                "null"
                ]
            },
            "attempts": {
                "bsonType": [
                    "int",
                    "long"
                ],
                "minimum": 0,
                "maximum": 3
            },
            "max_attempts": {
                "bsonType": [
                    "int",
                    "long"
                ],
                "minimum": 1,
                "maximum": 3
            },
            "last_error": {
                "bsonType": [
                    "string",
                "null"
                ],
                "enum": [
                    None,
                    "capacity_limited",
                    "storage_unavailable",
                    "authorization_unavailable",
                    "consent_required",
                    "evidence_mismatch",
                    "not_configured",
                    "provider_timeout",
                    "provider_rate_limited",
                    "provider_unavailable",
                    "invalid_output",
                    "admission_limited",
                    "interrupted",
                    "attempts_exhausted",
                    "legacy_fallback",
                    "unexpected_error"
                ]
            },
            "failure_reason": {
                "bsonType": [
                    "string",
                "null"
                ],
                "enum": [
                    None,
                    "capacity_limited",
                    "storage_unavailable",
                    "authorization_unavailable",
                    "consent_required",
                    "evidence_mismatch",
                    "not_configured",
                    "provider_timeout",
                    "provider_rate_limited",
                    "provider_unavailable",
                    "invalid_output",
                    "admission_limited",
                    "interrupted",
                    "attempts_exhausted",
                    "legacy_fallback",
                    "unexpected_error"
                ]
            },
            "completed_at": {
                "bsonType": [
                    "date",
                "null"
                ]
            }
        },
        "oneOf": [
            {
                "properties": {
                    "status": {
                        "enum": [
                            "queued"
                        ]
                    },
                    "attempts": {
                        "maximum": 2
                    },
                    "lease_token": {
                        "bsonType": "null"
                    },
                    "lease_expires_at": {
                        "bsonType": "null"
                    },
                    "failure_reason": {
                        "bsonType": "null"
                    },
                    "completed_at": {
                        "bsonType": "null"
                    }
                }
            },
            {
                "properties": {
                    "status": {
                        "enum": [
                            "claimed"
                        ]
                    },
                    "attempts": {
                        "minimum": 1
                    },
                    "lease_token": {
                        "bsonType": "string"
                    },
                    "lease_expires_at": {
                        "bsonType": "date"
                    },
                    "failure_reason": {
                        "bsonType": "null"
                    },
                    "completed_at": {
                        "bsonType": "null"
                    }
                }
            },
            {
                "properties": {
                    "status": {
                        "enum": [
                            "ready"
                        ]
                    },
                    "lease_token": {
                        "bsonType": "null"
                    },
                    "lease_expires_at": {
                        "bsonType": "null"
                    },
                    "failure_reason": {
                        "bsonType": "null"
                    },
                    "completed_at": {
                        "bsonType": "date"
                    }
                }
            },
            {
                "properties": {
                    "status": {
                        "enum": [
                            "failed"
                        ]
                    },
                    "lease_token": {
                        "bsonType": "null"
                    },
                    "lease_expires_at": {
                        "bsonType": "null"
                    },
                    "failure_reason": {
                        "bsonType": "string"
                    },
                    "completed_at": {
                        "bsonType": "date"
                    }
                }
            }
        ]
    }
}
JOB_INDEXES = [
    {
        "key": {
            "game_id": 1,
            "revision": 1
        },
        "name": "commentary_jobs_battle_unique_v1",
        "unique": True,
        "collation": {
            "locale": "simple"
        }
    },
    {
        "key": {
            "available_at": 1,
            "_id": 1
        },
        "name": "commentary_jobs_runnable_v1",
        "unique": False,
        "partialFilterExpression": {
            "status": "queued"
        },
        "collation": {
            "locale": "simple"
        }
    },
    {
        "key": {
            "lease_expires_at": 1,
            "_id": 1
        },
        "name": "commentary_jobs_expired_lease_v1",
        "unique": False,
        "partialFilterExpression": {
            "status": "claimed"
        },
        "collation": {
            "locale": "simple"
        }
    }
]


def job_validator():
    return deepcopy(JOB_VALIDATOR)


def job_indexes():
    return deepcopy(JOB_INDEXES)
