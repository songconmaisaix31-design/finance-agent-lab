"""Deprecated compatibility entrypoint for the legacy finance pipeline."""


def main(argv: list[str] | None = None) -> int:
    """Refuse implicit accounting runs and direct users to the guarded CLI."""
    del argv
    print(
        "DEPRECATED: src.pipeline is the legacy local script and will not run accounting by default.\n"
        "Use: python -m src.cli plan --city guan --input <input-directory> --output <output-directory>\n"
        "Use: python -m src.cli run --city guan --input <input-directory> --output <output-directory> --execute"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
