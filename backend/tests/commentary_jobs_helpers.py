"""Offline atomic protocol doubles. Not MongoDB/query-planner proof."""
import copy
from threading import RLock
from types import SimpleNamespace

from bson import BSON, ObjectId
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.commentary_jobs.capacity import MongoCommentaryCapacity
from app.commentary_jobs.discovery import MongoCommentaryReceiptSource, ReceiptReconciler
from app.commentary_jobs.policy import MongoCommentaryPolicyStore, CommentaryConsentService
from app.commentary_jobs.readiness import auxiliary_validators
from app.commentary_jobs.schema import job_indexes, job_validator
from app.commentary_jobs.settings import CommentaryJobSettings
from app.commentary_jobs.storage import MongoCommentaryJobRepository
from app.commentary_jobs.worker import CommentaryWorker
from app.models.actions import Roll, StartAttack
from app.repositories.commentary_repository import MongoCommentaryRepository
from app.services.commentary_service import CommentaryService
from npc_helpers import npc_state
from phase2_helpers import FixedDice, NOW, make_runtime, revise
from test_commentary_service import Narrator
from test_mongo_provisioning import matches as schema_matches
from test_phase4_services import command, owned_document, seed_principal, service_for


def field(doc, key):
    for part in key.split("."):
        doc = doc.get(part) if isinstance(doc, dict) else None
    return doc


def matches(doc, query):
    for key, expected in query.items():
        if key == "$and":
            if not all(matches(doc, sub) for sub in expected):
                return False
            continue
        if key == "$expr":
            left, right = expected["$lt"]
            if not field(doc, left[1:]) < field(doc, right[1:]):
                return False
            continue
        value = field(doc, key)
        if not isinstance(expected, dict):
            if value != expected:
                return False
            continue
        for op, rhs in expected.items():
            if op == "$gt":
                valid = value is not None and value > rhs
            elif op == "$gte":
                valid = value is not None and value >= rhs
            elif op == "$lt":
                valid = value is not None and value < rhs
            elif op == "$lte":
                valid = value is not None and value <= rhs
            elif op == "$in":
                valid = value in rhs
            else:
                raise AssertionError("Unsupported fake predicate")
            if not valid:
                return False
    return True


class Cursor(list):
    def sort(self, keys, direction=None):
        keys = [(keys, direction)] if isinstance(keys, str) else keys
        result = list(self)
        for key, direction in reversed(keys):
            result.sort(key=lambda doc: field(doc, key), reverse=direction == -1)
        return Cursor(result)

    def limit(self, count):
        return Cursor(self[:count])


class Rows:
    def __init__(self, name):
        self.name, self.docs, self.calls, self.images = name, {}, [], []
        self.lock = RLock()
        self.fail_before = self.fail_after = None

    def _failure(self, stage, operation):
        if getattr(self, stage) == operation:
            setattr(self, stage, None)
            raise PyMongoError("PRIVATE_DRIVER_MESSAGE_MUST_NOT_ESCAPE")

    def _save(self, row):
        BSON.encode(row)
        validator = ({"commentary_jobs": job_validator(), **auxiliary_validators()}).get(self.name)
        if validator:
            assert schema_matches(row, validator["$jsonSchema"]), (self.name, row)
        if self.name == "commentary_jobs":
            for other in self.docs.values():
                if (other["_id"] != row["_id"] and
                        (other["game_id"], other["revision"]) == (row["game_id"], row["revision"])):
                    raise DuplicateKeyError("natural key")
        self.docs[row["_id"]] = copy.deepcopy(row)
        self.images.append(copy.deepcopy(row))

    def find_one(self, query, projection=None, **kwargs):
        with self.lock:
            self.calls.append(("find_one", copy.deepcopy(query), kwargs))
            self._failure("fail_before", "find_one")
            row = next((copy.deepcopy(doc) for doc in self.docs.values() if matches(doc, query)), None)
            if row and projection:
                if any(projection.values()):
                    row = {k: v for k, v in row.items() if projection.get(k) or k == "_id"}
                else:
                    row = {k: v for k, v in row.items() if projection.get(k) != 0}
            return row

    def find(self, query, **kwargs):
        with self.lock:
            self.calls.append(("find", copy.deepcopy(query), kwargs))
            self._failure("fail_before", "find")
            return Cursor(copy.deepcopy([row for row in self.docs.values() if matches(row, query)]))

    def insert_one(self, document):
        with self.lock:
            self.calls.append(("insert_one", copy.deepcopy(document), {}))
            self._failure("fail_before", "insert_one")
            if document["_id"] in self.docs:
                raise DuplicateKeyError("row key")
            self._save(document)
            self._failure("fail_after", "insert_one")
            return SimpleNamespace(acknowledged=True)

    def update_one(self, query, update, *, upsert=False, **kwargs):
        with self.lock:
            self.calls.append(("update_one", copy.deepcopy(query), copy.deepcopy(update)))
            self._failure("fail_before", "update_one")
            row = next((copy.deepcopy(doc) for doc in self.docs.values() if matches(doc, query)), None)
            matched = row is not None
            if row is None and upsert:
                row = copy.deepcopy(update["$setOnInsert"])
            if row is not None:
                row.update(copy.deepcopy(update.get("$set", {})))
                for key in update.get("$unset", {}):
                    row.pop(key, None)
                self._save(row)
            self._failure("fail_after", "update_one")
            return SimpleNamespace(acknowledged=True, matched_count=int(matched))

    def find_one_and_update(self, query, update, *, sort=None, **kwargs):
        with self.lock:
            self.calls.append(("find_one_and_update", copy.deepcopy(query), copy.deepcopy(update)))
            self._failure("fail_before", "find_one_and_update")
            rows = Cursor([copy.deepcopy(row) for row in self.docs.values() if matches(row, query)])
            if sort:
                rows = rows.sort(sort)
            if not rows:
                return None
            row = rows[0]
            row.update(copy.deepcopy(update.get("$set", {})))
            for key, amount in update.get("$inc", {}).items():
                row[key] += amount
            self._save(row)
            self._failure("fail_after", "find_one_and_update")
            return copy.deepcopy(row)

    def replace_one(self, query, replacement, **kwargs):
        with self.lock:
            self.calls.append(("replace_one", copy.deepcopy(query), {}))
            self._failure("fail_before", "replace_one")
            found = any(matches(row, query) for row in self.docs.values())
            if found:
                self._save(replacement)
            self._failure("fail_after", "replace_one")
            return SimpleNamespace(acknowledged=True, matched_count=int(found))

    def index_information(self):
        return {i["name"]: {**i, "key": list(i["key"].items())} for i in job_indexes()}


class Database:
    def __init__(self):
        self.collections, self.accesses = {}, []
        self.metadata = None

    def get_collection(self, name, **kwargs):
        self.accesses.append((name, kwargs))
        return self.collections.setdefault(name, Rows(name))

    def list_collections(self, **kwargs):
        if self.metadata is not None:
            return copy.deepcopy(self.metadata)
        return [{"name": name, "type": "collection", "options": {"validator": validator,
            "validationLevel": "strict", "validationAction": "error"}} for name, validator in
            {"commentary_jobs": job_validator(), **auxiliary_validators()}.items()]


def system(catalog, *, npc=False, rolls=1, reason=None):
    store, games = service_for(catalog, dice=FixedDice([6, 1] * 500))
    principal = seed_principal(store)
    state = npc_state(catalog) if npc else revise(make_runtime(catalog),
        country_changes={0: {"soldiers": 5}, 1: {"soldiers": 100}})
    game_id = str(owned_document(store, principal, state)["_id"])
    db, now = Database(), [NOW]
    db.get_collection("games").docs[ObjectId(game_id)] = copy.deepcopy(store.games[game_id])
    db.get_collection("users").docs[ObjectId(principal.user_id)] = copy.deepcopy(store.users[principal.user_id])
    for number in (0, 1):
        db.get_collection("commentary_execution_slots").insert_one({"_id": number, "token": None})
    policies = MongoCommentaryPolicyStore(db)
    consent = CommentaryConsentService(games, policies, lambda: now[0])
    consent.set_enabled(principal, game_id, True, 0)
    if npc:
        for revision in range(rolls + 1):
            games.npc_step(principal, game_id, revision)
    else:
        source, target = state.countries[:2]
        games.human_action(principal, game_id, command(StartAttack(source_id=source.id, target_id=target.id)))
        for index in range(rolls):
            games.human_action(principal, game_id, command(Roll(), revision=index+1, action_id=f"roll-{index}"))
    db.get_collection("games").docs[ObjectId(game_id)] = copy.deepcopy(store.games[game_id])
    for receipt in store.receipts.values():
        doc = receipt.model_dump(mode="json")
        doc["_id"] = f"{game_id}:{receipt.command.action_id}"
        db.get_collection("game_action_receipts").docs[doc["_id"]] = doc
    settings = CommentaryJobSettings(discovery_enabled=True, execution_enabled=True, batch_size=2)
    narrator = Narrator(reason)
    commentary = CommentaryService(games, MongoCommentaryRepository(db), narrator,
        clock=lambda: now[0], capacity=MongoCommentaryCapacity(db))
    jobs = MongoCommentaryJobRepository(db)
    worker = CommentaryWorker(jobs, policies, commentary, settings, lambda: now[0])
    source = MongoCommentaryReceiptSource(db)
    discovery = ReceiptReconciler(policies, source, jobs, commentary, settings, lambda: now[0],
        saved_reconciler=worker.reconcile_saved)
    return SimpleNamespace(store=store, games=games, principal=principal, game_id=game_id,
        db=db, now=now, policies=policies, consent=consent, settings=settings, narrator=narrator,
        commentary=commentary, jobs=jobs, worker=worker, source=source, discovery=discovery)


def discover_all(s, ticks=12):
    for _ in range(ticks):
        s.discovery.run_once()
