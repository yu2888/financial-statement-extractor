"""Extract metrics or raw content for all three financial statements."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pymupdf

from statement_metrics import (
    METRIC_CALCULATORS,
    calculate_roic,
)
from statement_parser import STATEMENT_KEYWORDS, extract_statement


STATEMENTS = tuple(STATEMENT_KEYWORDS)


def extract_financial_statements(
    pdf_path: str | Path, raw: bool = False
) -> tuple[dict[str, Any], list[str]]:
    """Extract all statements, returning metrics by default or raw content."""
    pdf_path = Path(pdf_path)
    extracted: dict[str, tuple[dict[str, Any], list[dict[str, Any]], list[str]]] = {}
    issues: list[str] = []

    for statement in STATEMENTS:
        result, rows, periods, statement_issues = extract_statement(pdf_path, statement)
        extracted[statement] = (result, rows, periods)
        issues.extend(
            f"{statement}: {issue}" for issue in statement_issues
        )

    statements: dict[str, Any] = {}
    for statement in STATEMENTS:
        result, rows, periods = extracted[statement]
        if raw:
            result["raw_content"] = [
                {"label": row["label"], "values": row["values"]} for row in rows
            ]
        else:
            result["metrics"] = METRIC_CALCULATORS[statement](
                rows, periods, result["unit"]
            )
        result.pop("pdf", None)
        statements[statement] = result

    if not raw:
        _, income_rows, income_periods = extracted["income_statement"]
        _, balance_rows, balance_periods = extracted["balance_sheet"]
        statements["income_statement"]["metrics"].update(
            calculate_roic(
                income_rows,
                income_periods,
                balance_rows,
                balance_periods,
            )
        )

    return {"pdf": str(pdf_path), "statements": statements}, issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract metrics or raw content for all statements in a 10-K PDF."
    )
    parser.add_argument("pdf", type=Path, help="Path to the 10-K PDF")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Return raw line-item content for all statements instead of metrics",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write the JSON result to this file instead of standard output",
    )
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc)
    start_time = time.perf_counter()
    try:
        result, issues = extract_financial_statements(args.pdf, raw=args.raw)
        duration_seconds = time.perf_counter() - start_time
        finished_at = datetime.now(timezone.utc)
        result["execution"] = {
            "started_at": started_at.isoformat(timespec="milliseconds"),
            "finished_at": finished_at.isoformat(timespec="milliseconds"),
            "duration_seconds": round(duration_seconds, 3),
        }
        output = json.dumps(result, indent=2, ensure_ascii=True)
        if args.output:
            args.output.write_text(output + "\n", encoding="utf-8")
        else:
            print(output)
    except (OSError, ValueError, pymupdf.FileDataError) as error:
        print(f"Extraction failed: {error}", file=sys.stderr)
        return 1

    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
