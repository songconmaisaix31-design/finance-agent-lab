import argparse
import json
import sys
from pathlib import Path

from .city_registry import CityRegistryError, city_catalog_items, get_city_profile, validate_city_profiles
from .pipeline_service import (
    InputValidationError,
    PathSafetyError,
    PipelineError,
    RequestValidationError,
    make_run_request,
    plan_request,
    run_request,
)
from .storage import StorageError, initialize_storage, validate_storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="Safe public entrypoint for the multi-city finance pipeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Validate a run request without executing accounting.")
    _add_common(plan)

    run = sub.add_parser("run", help="Execute accounting only when --execute is provided.")
    _add_common(run)
    run.add_argument("--execute", action="store_true", help="Required confirmation for formal execution.")
    run.add_argument("--audit", action="store_true", help="Collect findings without declaring success for unknown types.")
    run.add_argument(
        "--unknown-type-policy",
        choices=["error", "report_only"],
        default=None,
        help="Unknown business type policy. Defaults to error for run --execute.",
    )

    cities = sub.add_parser("cities", help="Inspect and validate configured cities.")
    cities_sub = cities.add_subparsers(dest="cities_command", required=True)
    cities_sub.add_parser("list", help="List configured city profiles.")
    city_show = cities_sub.add_parser("show", help="Show one city profile summary.")
    city_show.add_argument("--city", required=True, help="City id to inspect.")
    cities_sub.add_parser("validate", help="Validate city and pipeline profiles.")

    storage = sub.add_parser("storage", help="Initialize or validate city data storage.")
    storage_sub = storage.add_subparsers(dest="storage_command", required=True)
    storage_init = storage_sub.add_parser("init", help="Create missing city storage directories and catalog.")
    storage_init.add_argument("--root", required=True, help="Finance data root.")
    storage_validate = storage_sub.add_parser("validate", help="Validate city storage directories and catalog.")
    storage_validate.add_argument("--root", required=True, help="Finance data root.")
    return parser


def _add_common(parser: argparse.ArgumentParser):
    parser.add_argument("--city", required=True, help="Explicit city id, for example guan.")
    parser.add_argument("--input", required=True, help="Input directory.")
    parser.add_argument("--output", required=True, help="Output root directory.")


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run" and not args.execute:
        print("INVALID_REQUEST: run requires --execute and will not start accounting without it.", file=sys.stderr)
        return RequestValidationError.exit_code

    try:
        if args.command == "cities":
            return _handle_cities(args)
        if args.command == "storage":
            return _handle_storage(args)
        request = make_run_request(args)
        result = plan_request(request) if args.command == "plan" else run_request(request)
        print(result.message)
        if result.summary_path:
            print(f"summary={result.summary_path}")
        return result.exit_code
    except PathSafetyError as exc:
        print(f"{exc.error_code}: {exc}", file=sys.stderr)
        return exc.exit_code
    except InputValidationError as exc:
        print(f"{exc.error_code}: {exc}", file=sys.stderr)
        return exc.exit_code
    except RequestValidationError as exc:
        print(f"{getattr(exc, 'error_code', 'INVALID_REQUEST')}: {exc}", file=sys.stderr)
        return exc.exit_code
    except PipelineError as exc:
        print(f"{exc.error_code}: {exc}", file=sys.stderr)
        return exc.exit_code
    except CityRegistryError as exc:
        print(f"{getattr(exc, 'error_code', 'CITY_PROFILE_INVALID')}: {exc}", file=sys.stderr)
        return 2
    except StorageError as exc:
        print(f"{exc.error_code}: {exc}", file=sys.stderr)
        return 3


def _handle_cities(args) -> int:
    if args.cities_command == "list":
        print(json.dumps({"cities": city_catalog_items()}, ensure_ascii=False, indent=2))
        return 0
    if args.cities_command == "show":
        profile = get_city_profile(args.city)
        data = {
            "city_id": profile.city_id,
            "display_name": profile.display_name,
            "pipeline_profile": {
                "profile_id": profile.pipeline_profile.profile_id,
                "version": profile.pipeline_profile.version,
            },
            "storage_namespace": profile.storage_namespace,
            "rule_set_id": profile.rule_set_id,
            "rule_status": profile.rule_status,
            "capabilities": profile.capabilities,
            "production_ready": profile.production_ready,
        }
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    issues = validate_city_profiles()
    print(json.dumps({"valid": not issues, "issues": issues}, ensure_ascii=False, indent=2))
    return 0 if not issues else 2


def _handle_storage(args) -> int:
    root = Path(args.root)
    if args.storage_command == "init":
        result = initialize_storage(root)
    else:
        result = validate_storage(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
