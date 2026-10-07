"""Command-line entry point and rule configuration.

An employee file is always checked the same way. Running::

    python -m data_quality.main employeefile.xlsx

profiles every column, checks duplicates on the employee id, the e-mail and
the last name + first name pair, and applies the rules in :func:`build_rules`.
Identity columns (id, names, e-mail) are left out of the modality frequency
table: their quality is the duplicate check.

Extra duplicate groups can still be added with ``--duplicates``. Column names
below must match the file; a rule or duplicate group referring to a missing
column stops the run with an explicit error.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .checker import profile
from .exporter import write_report
from .loader import load_file
from .rules import EmailFormatRule, Rule, run_rules

# Columns that identify a person. Not categories, so they are not frequency-counted.
RESPID_COLUMN: str = "respid"
LAST_NAME_COLUMN: str = "Last name"
FIRST_NAME_COLUMN: str = "First name"
EMAIL_COLUMN: str = "E-mail address"

IDENTITY_COLUMNS: tuple[str, ...] = (
    RESPID_COLUMN,
    LAST_NAME_COLUMN,
    FIRST_NAME_COLUMN,
    EMAIL_COLUMN,
)

# Always checked. Two employees with the same id, the same e-mail, or the
# same last name + first name are reported.
DUPLICATE_COLUMN_GROUPS: tuple[tuple[str, ...], ...] = (
    (RESPID_COLUMN,),
    (EMAIL_COLUMN,),
    (LAST_NAME_COLUMN, FIRST_NAME_COLUMN),
)


def build_rules() -> list[Rule]:
    """Business rules applied to every employee file.

    An empty cell is not a violation. Add a rule here only when a check is
    actually required. The e-mail format check is the one in place today:
    a blank address is ignored, a filled address that is not ``local@domain.tld``
    is reported.
    """
    return [
        EmailFormatRule(EMAIL_COLUMN),
        # AllowedValuesRule("Gender", {"Female", "Male"}),
    ]


def run(
    input_path: str | Path,
    output_path: str | Path | None = None,
    respid_column: str | None = None,
    duplicate_column_groups: Sequence[Sequence[str]] | None = None,
    modality_exclude: Sequence[str] | None = None,
    rules: Sequence[Rule] | None = None,
    sheet: str | int = 0,
) -> Path:
    """Load a file, run profiling and rules, write the report; return its path.

    This is the function to call when integrating the tool into another system.
    Arguments left as ``None`` use the employee-file defaults (identity columns
    and the standard duplicate groups).
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_name(f"{input_path.stem}_quality_report.txt")
    if duplicate_column_groups is None:
        duplicate_column_groups = DUPLICATE_COLUMN_GROUPS
    if modality_exclude is None:
        modality_exclude = IDENTITY_COLUMNS

    frame = load_file(input_path, sheet=sheet)
    result = profile(
        frame,
        respid_column=respid_column or RESPID_COLUMN,
        duplicate_column_groups=duplicate_column_groups,
        modality_exclude=modality_exclude,
        email_column=EMAIL_COLUMN,
        missing_exclude=IDENTITY_COLUMNS,
    )
    violations = run_rules(frame, rules if rules is not None else build_rules(), respid_column)
    return write_report(result, violations, input_path, output_path)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Data quality report for employee files (CSV / Excel).")
    parser.add_argument("input", help="Path to the CSV or Excel file to check.")
    parser.add_argument("-o", "--output", help="Report path (default: <input>_quality_report.txt).")
    parser.add_argument("--respid", help="Name of the respondent-id column (default: first column).")
    parser.add_argument("--sheet", default=0, help="Excel sheet name or index (default: 0).")
    parser.add_argument(
        "--duplicates",
        action="append",
        default=[],
        metavar="COL[,COL...]",
        help="Extra column group to check for duplicates, on top of respid, "
        "E-mail address, and Last name + First name. Repeat for several groups.",
    )
    return parser.parse_args(argv)


def _split_columns(value: str) -> list[str]:
    """Turn ``"a, b"`` into ``["a", "b"]`` (empty string -> empty list)."""
    return [column.strip() for column in value.split(",") if column.strip()]


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    sheet: str | int = int(args.sheet) if str(args.sheet).isdigit() else args.sheet
    extra_groups = [_split_columns(group) for group in args.duplicates]

    report_path = run(
        input_path=args.input,
        output_path=args.output,
        respid_column=args.respid,
        duplicate_column_groups=(*DUPLICATE_COLUMN_GROUPS, *extra_groups),
        sheet=sheet,
    )
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
