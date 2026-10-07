"""Text of the quality report. One function per section.

Section 7 groups whatever run_rules returned, and section 8 lists it under
the line, so a new rule does not need a new section.
"""

from collections import defaultdict
from datetime import datetime

from data_quality_simple.checks import DUPLICATE_GROUPS, EMAIL, IDENTITY, RESPID

WIDTH = 80


def render_report(path, profile, violations):
    parts = [
        _header(path, profile),
        _section("1. COLUMN METRICS", _column_metrics(profile)),
        _section("2. MODALITIES", _modalities(profile)),
        _section("3. E-MAIL DOMAINS", _email_domains(profile)),
        _section("4. CONSTANT COLUMNS", _constant_columns(profile)),
        _section("5. DUPLICATES", _duplicates(profile)),
        _section("6. MISSING VALUES", _missing_values(profile)),
        _section("7. BUSINESS RULE VIOLATIONS", _rule_violations(violations)),
        _section("8. ISSUES BY LINE", _issues_by_line(profile.duplicate_issues, violations)),
    ]
    return "\n".join(parts) + "\n"


def _header(path, profile):
    return "\n".join(
        [
            "=" * WIDTH,
            "DATA QUALITY REPORT",
            "=" * WIDTH,
            f"Source file   : {path}",
            f"Generated     : {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"Rows          : {profile.row_count}",
            f"respid column : {RESPID}",
            f"Columns ({len(profile.columns)}) : {', '.join(profile.columns)}",
        ]
    )


def _section(title, body):
    return "\n".join(["", "-" * WIDTH, title, "-" * WIDTH, *body])


def _column_metrics(profile):
    name_width = max(len("Column"), *(len(item.name) for item in profile.stats))
    dtype_width = max(len("Type"), *(len(item.dtype) for item in profile.stats))
    lines = [
        f"{'Column':<{name_width}}  {'Type':<{dtype_width}}  {'Missing':>8}  {'Missing %':>9}  {'Unique':>7}"
    ]
    for item in profile.stats:
        lines.append(
            f"{item.name:<{name_width}}  {item.dtype:<{dtype_width}}  "
            f"{item.missing:>8}  {item.missing_pct:>8.2f}%  {item.unique:>7}"
        )
    return lines


def _modality_label(value):
    if value is None:
        return "(missing)"
    if not value.strip():
        return "(blank)"
    if value.endswith(".0") and value[:-2].lstrip("-").isdigit():
        return value[:-2]
    return value


def _modalities(profile):
    """Every distinct value, except the identity columns (those are duplicates)."""
    count_width = max(len(str(profile.row_count)), 1)
    lines = []
    omitted = [item.name for item in profile.stats if item.name in IDENTITY]
    if omitted:
        lines.append(
            "Omitted (identity columns, checked for duplicates instead): " + ", ".join(omitted)
        )
    for item in profile.stats:
        if item.name in IDENTITY:
            continue
        if lines:
            lines.append("")
        lines.append(f"{item.name}  ({item.unique} distinct, {item.missing} missing)")
        for value, count, share in item.modalities:
            lines.append(f"  {count:>{count_width}}  {share:>6.2f}%  {_modality_label(value)}")
    return lines


def _email_domains(profile):
    lines = [
        f"{EMAIL}  ({profile.valid_email_count} valid, "
        f"{profile.skipped_email_count} skipped: empty or invalid)"
    ]
    if not profile.email_domains:
        lines.append("(no valid address)")
        return lines
    count_width = max(len(str(profile.valid_email_count)), 1)
    for suffix, count, share in profile.email_domains:
        lines.append(f"  {count:>{count_width}}  {share:>6.2f}%  {suffix}")
    return lines


def _constant_columns(profile):
    names = [item.name for item in profile.stats if item.unique == 1]
    return [f"- {name}" for name in names] or ["(none)"]


def _duplicates(profile):
    lines = []
    for columns in DUPLICATE_GROUPS:
        matched = [group for group in profile.duplicate_groups if group.columns == columns]
        lines.append(f"Group [{', '.join(columns)}]: {len(matched)} duplicated value(s)")
        for group in matched:
            joined = " / ".join(group.values)
            line_numbers = ", ".join(str(line) for line in group.lines)
            lines.append(f"  - '{joined}' -> line(s) {line_numbers}")
    return lines


def _missing_values(profile):
    rows = profile.missing_rows
    if not rows:
        return ["(none)"]
    lines = [
        f"{len(rows)} row(s) with at least one empty field (respid, names and e-mail ignored)",
        "",
    ]
    for row in rows:
        names = ", ".join(row.columns)
        lines.append(f"  Line {row.line} (respid {row.respid}): {len(row.columns)} missing: {names}")
    return lines


def _rule_violations(violations):
    if not violations:
        return ["(none)"]
    by_rule = {}
    for issue in violations:
        by_rule.setdefault(issue.category, []).append(issue)
    lines = []
    for name, issues in by_rule.items():
        if lines:
            lines.append("")
        lines.append(f"{name} ({len(issues)} row(s))")
        for issue in sorted(issues, key=lambda item: item.line):
            lines.append(f"  Line {issue.line} (respid {issue.respid}): {issue.message}")
    return lines


def _issues_by_line(duplicate_issues, violations):
    all_issues = [*duplicate_issues, *violations]
    if not all_issues:
        return ["(no row-level issue found)"]
    by_line = defaultdict(list)
    for issue in all_issues:
        by_line[issue.line].append(issue)
    lines = [f"{len(by_line)} line(s) with at least one issue", ""]
    for line in sorted(by_line):
        lines.append(f"Line {line} (respid {by_line[line][0].respid}):")
        for issue in by_line[line]:
            where = f" ({issue.column})" if issue.column else ""
            lines.append(f"  - [{issue.category}]{where} {issue.message}")
    return lines
