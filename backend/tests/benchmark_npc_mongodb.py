"""Identical offline scenarios against a selected checkout, never a live MongoDB.

Run this harness with --backend-root pointing to a full e57206c export or the
candidate. --managed-indexes models the candidate lifespan's startup attestation.
Commit commands are counted at the fake transaction boundary; wire behavior is not
simulated. Synthetic delays are applied once per collection command and commit.
"""
import argparse
import json
from pathlib import Path
import socket
import sys
from time import sleep
from unittest.mock import patch


def run_case(catalog, state, name, delay_ms=0, *, managed_indexes=True):
    import benchmark_npc as bench
    import test_phase4_mongo as mongo
    from app import npc_diagnostics as diag

    setup = bench.setup_store
    transaction = mongo.Session.with_transaction
    commits = []
    startup_metadata = []

    def prepared(*args, **kwargs):
        bundle = setup(*args, **kwargs)
        repository, _, _, _, database, _ = bundle
        if managed_indexes:
            from app.repositories.phase4_indexes import IndexReadiness
            readiness = IndexReadiness(database)
            readiness.ensure()
            repository._index_readiness = readiness
            startup_metadata.append(sum(op == "index_information" for c in database.values() for op, *_ in c.calls))
        # Fixture construction authorizes a seed principal before the measured request.
        # Collection probes also start after this setup in run_once.
        record.spans.clear()
        return bundle

    def committed(self, callback, **kwargs):
        result = transaction(self, callback, **kwargs)
        if delay_ms:
            sleep(delay_ms / 1000)
        commits.append(True)
        return result

    record = diag.RequestTimings()
    token = diag._current.set(record)
    try:
        with patch.object(bench, "setup_store", prepared), patch.object(mongo.Session, "with_transaction", committed):
            result = bench.run_once(catalog, state, name, delay_ms)
    finally:
        diag._current.reset(token)
    def count(*methods):
        return sum(v for k, v in result["commands"].items() if k.rsplit(".", 1)[-1] in methods)
    spans = record.summary(200, "returned", True)["spans_inclusive"]
    return {**result, "mongo_total": result["db_commands"] + len(commits),
            "listIndexes": count("index_information"), "find": count("find_one", "find"),
            "aggregate": count("aggregate"),
            "writes": count("update_one", "insert_one", "find_one_and_update"),
            "commits": len(commits), "owned_game_loads": spans.get("owned_game_load", {}).get("count", 0),
            "authorizations": spans.get("authorization", {}).get("count", 0),
            "index_verifications": spans.get("index_verification", {}).get("count", 0),
            "spans_inclusive": spans, "startup_index_commands": sum(startup_metadata)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--command-delay-ms", type=float, default=0)
    parser.add_argument("--managed-indexes", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.samples <= 100 or not 0 <= args.command_delay_ms <= 100:
        parser.error("Bounded samples 1..100 and synthetic delay 0..100 ms required")
    backend = args.backend_root.resolve()
    sys.path[:0] = [str(backend / "tests"), str(backend)]
    import benchmark_npc as bench
    catalog = bench.CountryCatalog.load()
    rows = {}
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Offline benchmark")), patch.object(
            socket, "create_connection", side_effect=AssertionError("Offline benchmark")):
        for name, state in bench.scenarios(catalog).items():
            run_case(catalog, state, name, args.command_delay_ms, managed_indexes=args.managed_indexes)
            runs = [run_case(catalog, state, name, args.command_delay_ms, managed_indexes=args.managed_indexes)
                    for _ in range(args.samples)]
            if len({r["result_sha256"] for r in runs}) != 1:
                raise AssertionError("Non-deterministic scenario " + name)
            first = runs[0]
            rows[name] = {**bench.summary([r["total_ms"] for r in runs]),
                          **{k: first[k] for k in ("mongo_total", "listIndexes", "find", "aggregate", "writes", "commits",
                             "owned_game_loads", "authorizations", "index_verifications", "startup_index_commands",
                             "commands", "result_sha256", "receipt_count", "dice_calls", "actions")},
                          "spans_inclusive_median_ms": {s: bench.summary([r["spans_inclusive"].get(s, {}).get("total_ms", 0)
                                                                         for r in runs])["median_ms"]
                                                        for s in first["spans_inclusive"]}}
    result = {"scope": "Actual services/engine; in-memory collection and transaction doubles. No live DB/HTTP.",
              "backend_root": str(backend), "samples": args.samples, "managed_indexes": args.managed_indexes,
              "synthetic_delay_ms": args.command_delay_ms,
              "limitations": ["Successful single-callback transactions only; commits counted at fake boundary",
                 "No wire getMore, topology, retries, DNS/TLS, proxy, pool waiting or real Mongo transaction measurement",
                 "Startup metadata excluded from steady-state timings; no user/account state is cached",
                 "Inclusive spans overlap and must not be summed; optimized production latency NOT MEASURED"],
              "cases": rows}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({n: {k: r[k] for k in ("mongo_total", "listIndexes", "find", "writes", "commits", "median_ms")}
                      for n, r in rows.items()}))


if __name__ == "__main__":
    main()
