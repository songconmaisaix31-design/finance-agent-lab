import argparse
import sys

from .pipeline_service import (
    InputValidationError,
    PathSafetyError,
    PipelineError,
    RequestValidationError,
    make_run_request,
    plan_request,
    run_request,
)


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


if __name__ == "__main__":
    raise SystemExit(main())
