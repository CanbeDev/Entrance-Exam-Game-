"""Offline service-path benchmark. No HTTP, MongoDB, environment or provider access.

Uses the actual authorization/repository/engine classes with existing collection
doubles. Injected DB command latency is a model, never a production measurement.
Run from backend: .venv/Scripts/python.exe -B tests/benchmark_npc.py --samples 20
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from math import ceil
from pathlib import Path
import re
import socket
import statistics
import sys
import subprocess
from time import perf_counter, sleep
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bson import ObjectId
from app.engine.npc.strategy import NpcStrategy
from app.models.actions import StartAttack
from app.repositories.security_repository import MongoSecurityRepository
from app.repositories import scoped_action_repository
from app.security.config import SecuritySettings
from app.services.authorized_game_service import AuthorizedGameService
from app.services.country_catalog import CountryCatalog
from app.services.public_game_service import public_result
from npc_helpers import npc_state
from phase2_helpers import FixedDice, NOW, revise, step
from test_phase4_mongo import setup_store


def scenarios(catalog):
    attack = npc_state(catalog)
    normal = npc_state(catalog, source_soldiers=5, changes={0: {"soldiers": 3}})
    roll = step(normal, StartAttack(source_id=normal.countries[1].id, target_id=normal.countries[0].id)).state
    conquer = step(attack, StartAttack(source_id=attack.countries[1].id, target_id=attack.countries[0].id)).state
    rows = {
        "allocation": npc_state(catalog, changes={2: {"owner_id": "npc-1"}}, round=5,
                                phase="allocating", pending_reinforcements=4),
        "attack_start": attack,
        "dice_exchange": roll,
        "conquest": conquer,
        "transfer": npc_state(catalog, changes={2: {"owner_id": "npc-1", "soldiers": 6}}),
        "end_turn": npc_state(catalog, phase="post_attack", attack_used=True),
        "skip": npc_state(catalog, soldiers=100, source_soldiers=2),
        "nine_npc_sequence": npc_state(catalog, source_soldiers=1),
    }
    return {name: revise(state, created_at=NOW, updated_at=NOW) for name, state in rows.items()}


def summary(values):
    values = sorted(values)
    return {"median_ms": round(statistics.median(values), 3),
            "p95_ms": round(values[ceil(len(values) * .95) - 1], 3),
            "max_ms": round(max(values), 3)}


class Probe:
    def __init__(self, delay_ms):
        self.delay = delay_ms / 1000
        self.calls = Counter()
        self.time = defaultdict(float)
        self.db_depth = 0
        self.auth_depth = 0

    def db(self, name, original):
        def invoke(*args, **kwargs):
            # The double's find_one_and_update calls update_one internally;
            # the actual MongoDB operation is one command, not two.
            outer = self.db_depth == 0
            self.db_depth += 1
            started = perf_counter()
            try:
                if outer and self.delay:
                    sleep(self.delay)
                return original(*args, **kwargs)
            finally:
                self.db_depth -= 1
                if outer:
                    self.calls[name] += 1
                    group = "metadata" if name.endswith("index_information") else (
                        "write" if name.endswith(("update_one", "insert_one", "find_one_and_update")) else "read")
                    self.time["db_" + group] += (perf_counter() - started) * 1000
        return invoke


def run_once(catalog, state, name, delay_ms):
    repository, principal, _, game_id, database, client = setup_store(catalog)
    saved = database["games"].docs[ObjectId(game_id)]
    saved.update(state.model_dump())
    # All identities below are synthetic test fixtures; none are emitted.
    settings = SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True,
                                trusted_origins=("https://offline.invalid",))
    dice_values = [6, 2, 3, 1, 5, 3] if name == "dice_exchange" else [6, 1] * 200
    dice = FixedDice(dice_values)
    service = AuthorizedGameService(repository, settings, lambda: NOW, dice=dice, catalog=catalog)
    probe = Probe(delay_ms)
    for collection_name, collection in database.items():
        for method in ("find_one", "find", "aggregate", "update_one", "insert_one", "find_one_and_update", "index_information"):
            original = getattr(collection, method)
            setattr(collection, method, probe.db(collection_name + "." + method, original))
        collection.calls.clear()

    decide = NpcStrategy.decide
    authorize = MongoSecurityRepository.authorize

    def timed_decide(self, observed):
        started = perf_counter()
        try:
            return decide(self, observed)
        finally:
            probe.time["decision_including_validation"] += (perf_counter() - started) * 1000
            probe.calls["strategy_decide"] += 1

    def timed_authorize(self, *args, **kwargs):
        outer = probe.auth_depth == 0
        probe.auth_depth += 1
        started = perf_counter()
        try:
            return authorize(self, *args, **kwargs)
        finally:
            probe.auth_depth -= 1
            if outer:
                probe.time["authorization_inclusive"] += (perf_counter() - started) * 1000

    results = []
    started = perf_counter()
    with patch.object(NpcStrategy, "decide", timed_decide), patch.object(MongoSecurityRepository, "authorize", timed_authorize):
        operations = 9 if name == "nine_npc_sequence" else 1
        for _ in range(operations):
            # Equivalent repository path of the authenticated dependency's touch;
            # no password/token transport or real HTTP session is involved.
            actual = repository.authorize(principal.session_hash, NOW, settings.idle_seconds, touch=True)
            revision = database["games"].docs[ObjectId(game_id)]["revision"]
            result = service.npc_step(actual, game_id, revision)
            mark = perf_counter()
            serialized = json.dumps(public_result(result), sort_keys=True, separators=(",", ":"))
            probe.time["serialization"] += (perf_counter() - mark) * 1000
            results.append(serialized)
    total = (perf_counter() - started) * 1000
    commands = {key: value for key, value in probe.calls.items() if "." in key}
    return {"total_ms": total, "parts_ms": dict(probe.time), "commands": commands,
            "db_commands": sum(commands.values()), "decisions": probe.calls["strategy_decide"],
            "actions": len(results), "result_sha256": hashlib.sha256("\n".join(results).encode()).hexdigest(),
            "receipt_count": len(database["game_action_receipts"].docs), "dice_calls": dice.calls}


def benchmark(samples, delay_ms):
    catalog = CountryCatalog.load()
    rows = {}
    # Guards are defense in depth. Only injected dictionaries/collection doubles
    # are used; neither MongoClient nor application lifespan is constructed.
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Offline benchmark forbids network")), \
         patch.object(socket, "create_connection", side_effect=AssertionError("Offline benchmark forbids network")):
        for name, state in scenarios(catalog).items():
            run_once(catalog, state, name, delay_ms)  # Warm imports and model paths.
            runs = [run_once(catalog, state, name, delay_ms) for _ in range(samples)]
            if len({r["result_sha256"] for r in runs}) != 1:
                raise AssertionError("Non-deterministic output: " + name)
            first = runs[0]
            rows[name] = {**summary([r["total_ms"] for r in runs]),
                          "parts_ms": {key: summary([r["parts_ms"].get(key, 0) for r in runs])
                                       for key in first["parts_ms"]},
                          **{key: first[key] for key in ("commands", "db_commands", "decisions", "actions",
                                                       "result_sha256", "receipt_count", "dice_calls")}}
    return {"scope": "actual service/repository/engine with in-memory Mongo command doubles; not live HTTP/DB",
            "samples": samples, "injected_command_delay_ms": delay_ms,
            "limitations": ["No DNS/TLS/proxy, real commits, pool waits or transaction retries are measured",
                            "DB command model excludes begin/commit wire messages and cursor getMore",
                            "Authorization timings include DB time and must not be added to parts",
                            "Injected latency is synthetic; it cannot establish production attribution"],
            "cases": rows}


def compare(samples, delay_ms, reference):
    """Interleave old/new samples to reduce warmup and machine-load bias."""
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", reference) is None:
        raise ValueError("Comparison requires an explicit hexadecimal commit ID")
    source = subprocess.check_output(["git", "show", reference + ":backend/app/repositories/scoped_action_repository.py"])
    namespace = {"__name__": "offline_scoped_repository_baseline"}
    exec(compile(source, "baseline-scoped-repository.py", "exec"), namespace)
    old = namespace["ScopedMongoActionRepository"]
    new = scoped_action_repository.ScopedMongoActionRepository
    catalog = CountryCatalog.load()
    rows = {}
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Offline benchmark forbids network")), \
         patch.object(socket, "create_connection", side_effect=AssertionError("Offline benchmark forbids network")):
        for name, state in scenarios(catalog).items():
            runs = {"baseline": [], "optimized": []}
            for cls in (old, new):
                with patch.object(scoped_action_repository, "ScopedMongoActionRepository", cls):
                    run_once(catalog, state, name, delay_ms)
            for sample in range(samples):
                versions = [("baseline", old), ("optimized", new)]
                if sample % 2:
                    versions.reverse()
                for label, cls in versions:
                    with patch.object(scoped_action_repository, "ScopedMongoActionRepository", cls):
                        runs[label].append(run_once(catalog, state, name, delay_ms))
            if len({r["result_sha256"] for values in runs.values() for r in values}) != 1:
                raise AssertionError("Before/after gameplay differs: " + name)
            rows[name] = {label: {**summary([r["total_ms"] for r in values]),
                                 **{key: values[0][key] for key in ("commands", "db_commands", "result_sha256",
                                                                   "receipt_count", "dice_calls", "decisions")},
                                 "parts_ms": {part: summary([r["parts_ms"].get(part, 0) for r in values])
                                              for part in values[0]["parts_ms"]}}
                          for label, values in runs.items()}
            print(json.dumps({"case": name, "equivalent_result": True,
                              **{label: values["median_ms"] for label, values in rows[name].items()}}), flush=True)
    return {"scope": "paired alternating service-path samples using in-memory Mongo doubles, not production HTTP/DB",
            "baseline_ref": reference, "samples_per_version": samples,
            "injected_command_delay_ms": delay_ms,
            "limitations": ["Synthetic delay is not measured network latency", "p95 uses nearest rank; n=10 p95 equals max",
                            "No real database commit, pool, DNS/TLS, proxy or transaction-retry timing",
                            "Authorization includes overlapping DB time; do not sum inclusive parts"], "cases": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--command-delay-ms", type=float, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare-ref", help="Explicit local Git commit; interleave baseline and current samples")
    args = parser.parse_args()
    if not 1 <= args.samples <= 100 or not 0 <= args.command_delay_ms <= 100:
        parser.error("Bounded samples 1..100 and synthetic delay 0..100 ms required")
    result = compare(args.samples, args.command_delay_ms, args.compare_ref) if args.compare_ref else benchmark(args.samples, args.command_delay_ms)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if not args.compare_ref:
        print(json.dumps({name: {key: row[key] for key in ("median_ms", "p95_ms", "max_ms", "db_commands")}
                          for name, row in result["cases"].items()}))
