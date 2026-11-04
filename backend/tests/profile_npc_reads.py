"""Offline command/call-site inventory. Emits no query values or private documents."""
import argparse
from collections import Counter
import inspect
import json
from pathlib import Path
import sys
from unittest.mock import patch


def profile(catalog, state, scenario):
    import benchmark_npc as bench
    from benchmark_npc_mongodb import run_case
    from app import npc_diagnostics as diag
    setup = bench.setup_store
    rows = []
    def instrumented(*args, **kwargs):
        bundle = setup(*args, **kwargs)
        for name, collection in bundle[4].items():
            for method in ("find_one", "aggregate"):
                if not hasattr(collection, method):
                    continue
                original = getattr(collection, method)
                def captured(*a, original=original, method=method, name=name, **kw):
                    frames = []
                    for info in inspect.stack(context=0):
                        path = Path(info.filename)
                        if "app" in path.parts and path.suffix == ".py":
                            index = path.parts.index("app")
                            frames.append("/".join(path.parts[index:]) + ":" + str(info.lineno) + " " + info.function)
                    active = diag._active_spans.get()
                    transaction = "game" if "game_transaction" in active else "authentication" if "auth_transaction" in active else "none"
                    rows.append({"ordinal": len(rows)+1, "collection": name,
                        "command": "aggregate" if method == "aggregate" else "find",
                        "transaction": transaction, "session_supplied": kw.get("session") is not None,
                        "call_sites": frames})
                    return original(*a, **kw)
                setattr(collection, method, captured)
        return bundle
    with patch.object(bench, "setup_store", instrumented):
        result = run_case(catalog, state, scenario)
    return {"scenario": scenario, "commands": {k: result.get(k, 0) for k in
        ("mongo_total", "find", "aggregate", "writes", "commits", "owned_game_loads", "authorizations")},
        "reads": rows, "groups": dict(Counter(r["collection"] + "." + r["command"] + "." + r["transaction"] for r in rows))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sys.path[:0] = [str(args.backend_root.resolve()/"tests"),str(args.backend_root.resolve())]
    import benchmark_npc as bench
    import socket
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Offline profile")), patch.object(
            socket, "create_connection", side_effect=AssertionError("Offline profile")):
        catalog = bench.CountryCatalog.load()
        results = {name: profile(catalog, bench.scenarios(catalog)[name], name) for name in ("allocation", "attack_start")}
    args.output.write_text(json.dumps(results, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: {"commands":v["commands"],"groups":v["groups"]} for k,v in results.items()}))
