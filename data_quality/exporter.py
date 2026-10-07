"""Render profiling results and rule violations as a plain-text report."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .checker import ProfileResult, RowIssue

WIDTH: int = 80
RULE_SEPARATOR: str = "=" * WIDTH
SECTION_SEPARATOR: str = "-" * WIDTH


def write_report(
    profile: ProfileResult,
    violations: Sequence[RowIssue],
    source: str | Path,
    output_path: str | Path,
) -> Path:
    """Render the report and write it to ``output_path`` (UTF-8)."""
    output_path = Path(output_path)
    output_path.write_text(render_report(profile, violations, source), encoding="utf-8")
    return output_path


def render_report(profile: ProfileResult, violations: Sequence[RowIssue], source: str | Path) -> str:
    """Build the full report as a single string."""
    sections = [
        _header(profile, source),
        _section("1. COLUMN METRICS", _column_metrics(profile)),
        _section("2. MODALITIES", _modalities(profile)),
        _section("3. E-MAIL DOMAINS", _email_domains(profile)),
        _section("4. CONSTANT COLUMNS", _constant_columns(profile)),
        _section("5. DUPLICATES", _duplicates(profile)),
        _section("6. MISSING VALUES", _missing_values(profile)),
        _section("7. BUSINESS RULE VIOLATIONS", _rule_violations(violations)),
        _section("8. ISSUES BY LINE", _issues_by_line([*profile.issues, *violations])),
    ]
    return "\n".join(sections) + "\n"


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


def _header(profile: ProfileResult, source: str | Path) -> str:
    lines = [
        RULE_SEPARATOR,
        "DATA QUALITY REPORT",
        RULE_SEPARATOR,
        f"Source file   : {source}",
        f"Generated     : {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Rows          : {profile.row_count}",
        f"respid column : {profile.respid_column}",
        f"Columns ({len(profile.columns)}) : {', '.join(profile.columns)}",
    ]
    return "\n".join(lines)


def _column_metrics(profile: ProfileResult) -> list[str]:
    name_width = max(len("Column"), *(len(metric.name) for metric in profile.column_metrics))
    dtype_width = max(len("Type"), *(len(metric.dtype) for metric in profile.column_metrics))
    header = f"{'Column':<{name_width}}  {'Type':<{dtype_width}}  {'Missing':>8}  {'Missing %':>9}  {'Unique':>7}"
    rows = [
        f"{metric.name:<{name_width}}  {metric.dtype:<{dtype_width}}  "
        f"{metric.missing_count:>8}  {metric.missing_pct:>8.2f}%  {metric.unique_count:>7}"
        for metric in profile.column_metrics
    ]
    return [header, *rows]


def _modalities(profile: ProfileResult) -> list[str]:
    """Distinct values of each categorical column, with count and percentage.

    Identity columns (id, names, email) are omitted: listing every person is
    not a modality distribution, and those columns are covered by the
    duplicate check.
    """
    excluded = set(profile.modality_exclude)
    shown = [metric for metric in profile.column_metrics if metric.name not in excluded]
    if not shown:
        return ["(no columns)"]
    count_width = max(len(str(profile.row_count)), 1)
    lines: list[str] = []
    omitted = [metric.name for metric in profile.column_metrics if metric.name in excluded]
    if omitted:
        lines.append("Omitted (identity columns, checked for duplicates instead): " + ", ".join(omitted))
    for metric in shown:
        if lines:
            lines.append("")
        lines.append(f"{metric.name}  ({metric.unique_count} distinct, {metric.missing_count} missing)")
        for modality in metric.modalities:
            lines.append(
                f"  {modality.count:>{count_width}}  {modality.pct:>6.2f}%  {_modality_label(modality.value)}"
            )
    return lines


def _modality_label(value: str | None) -> str:
    """Render one modality. Whole numbers stored as ``6026.0`` print as ``6026``."""
    if value is None:
        return "(missing)"
    if not value.strip():
        return "(blank)"
    if value.endswith(".0") and value[:-2].lstrip("-").isdigit():
        return value[:-2]
    return value


def _email_domains(profile: ProfileResult) -> list[str]:
    """Domain of each valid address, with count and percentage of valid addresses."""
    if not profile.email_column:
        return ["(no e-mail column configured)"]
    header = (
        f"{profile.email_column}  "
        f"({profile.valid_email_count} valid, {profile.skipped_email_count} skipped: empty or invalid)"
    )
    if not profile.email_domains:
        return [header, "(no valid address)"]
    count_width = max(len(str(profile.valid_email_count)), 1)
    rows = [
        f"  {item.count:>{count_width}}  {item.pct:>6.2f}%  {item.domain}"
        for item in profile.email_domains
    ]
    return [header, *rows]


def _constant_columns(profile: ProfileResult) -> list[str]:
    if not profile.constant_columns:
        return ["(none)"]
    return [f"- {name}" for name in profile.constant_columns]


def _duplicates(profile: ProfileResult) -> list[str]:
    if not profile.duplicate_column_groups:
        return ["(no duplicate check configured)"]
    lines: list[str] = []
    for columns in profile.duplicate_column_groups:
        groups = [group for group in profile.duplicate_groups if list(group.columns) == columns]
        lines.append(f"Group [{', '.join(columns)}]: {len(groups)} duplicated value(s)")
        for group in groups:
            values = " / ".join(group.values)
            lines.append(f"  - '{values}' -> line(s) {_join_lines(group.lines)}")
    return lines


def _missing_values(profile: ProfileResult) -> list[str]:
    """Empty cells outside the identity columns, most incomplete rows first.

    This is a completeness inventory, not a violation: the columns are not
    declared mandatory.
    """
    rows = profile.missing_rows
    if not rows:
        return ["(none)"]
    lines = [f"{len(rows)} row(s) with at least one empty field (respid, names and e-mail ignored)", ""]
    for row in rows:
        names = ", ".join(row.columns)
        lines.append(f"  Line {row.line} (respid {row.respid}): {len(row.columns)} missing: {names}")
    return lines


def _rule_violations(violations: Sequence[RowIssue]) -> list[str]:
    """Each rule, then every violating line with its explanation."""
    if not violations:
        return ["(none)"]
    by_rule: dict[str, list[RowIssue]] = {}
    for issue in violations:
        by_rule.setdefault(issue.category, []).append(issue)

    lines: list[str] = []
    for name, issues in by_rule.items():
        if lines:
            lines.append("")
        lines.append(f"{name} ({len(issues)} row(s))")
        for issue in sorted(issues, key=lambda item: item.line):
            lines.append(f"  Line {issue.line} (respid {issue.respid}): {issue.message}")
    return lines


def _issues_by_line(issues: Sequence[RowIssue]) -> list[str]:
    if not issues:
        return ["(no row-level issue found)"]

    by_line: dict[int, list[RowIssue]] = defaultdict(list)
    for issue in issues:
        by_line[issue.line].append(issue)

    lines = [f"{len(by_line)} line(s) with at least one issue", ""]
    for line in sorted(by_line):
        respid = by_line[line][0].respid
        lines.append(f"Line {line} (respid {respid}):")
        for issue in by_line[line]:
            location = f" ({issue.column})" if issue.column else ""
            lines.append(f"  - [{issue.category}]{location} {issue.message}")
    return lines


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #


def _section(title: str, body: Sequence[str]) -> str:
    return "\n".join(["", SECTION_SEPARATOR, title, SECTION_SEPARATOR, *body])


def _join_lines(lines: Sequence[int]) -> str:
    return ", ".join(str(line) for line in lines)
