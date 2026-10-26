"""Offline plan by default; explicitly authorized local disposable DDL only."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.repositories.mongo_provisioning import (
    ProvisioningError, inspect_database, provision_database, provisioning_plan, validate_target, verify_database,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    for name in ("inspect", "verify", "apply"):
        mode.add_argument("--" + name, action="store_true")
    parser.add_argument("--database")
    parser.add_argument("--confirm-database")
    args = parser.parse_args(argv)
    if not any((args.inspect, args.verify, args.apply)):
        print(json.dumps(provisioning_plan(), default=dict, indent=2))
        return
    try:
        validate_target(args.database)
        if args.apply and args.confirm_database != args.database:
            raise ProvisioningError("confirmation_required")
        from pymongo import MongoClient
        # No environment, URI argument, SRV, credentials or Atlas support.
        with MongoClient("mongodb://127.0.0.1:27017/?directConnection=true",
                         serverSelectionTimeoutMS=3000) as client:
            client.admin.command("ping")
            database = client[args.database]
            if args.inspect:
                print(json.dumps(inspect_database(database), default=str, indent=2))
            elif args.verify:
                verify_database(database)
                print("Database metadata and documents verified")
            else:
                provision_database(database, apply=True, confirmation=args.confirm_database)
                print("Local disposable database provisioned and verified")
    except ProvisioningError as error:
        raise SystemExit(str(error)) from None
    except Exception:
        # Never expose driver messages, which can contain secrets or document data.
        raise SystemExit("connection_or_operation_failed may_have_changes=unknown; inspect local disposable target. No fallback.") from None


if __name__ == "__main__":
    main()
