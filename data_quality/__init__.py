"""Data quality and profiling tool for employee data files (CSV / Excel).

Typical programmatic use::

    from data_quality import load_file, profile, run_rules, write_report, EmailFormatRule

    frame = load_file("employees.xlsx")
    result = profile(frame, duplicate_column_groups=[["email"]])
    violations = run_rules(frame, [EmailFormatRule("email")])
    write_report(result, violations, "employees.xlsx", "report.txt")
"""

from .checker import (
    ColumnMetrics,
    DomainCount,
    DuplicateGroup,
    MissingRow,
    ModalityCount,
    ProfileResult,
    RowIssue,
    profile,
)
from .exporter import render_report, write_report
from .loader import load_file
from .rules import (
    AllowedValuesRule,
    CustomRule,
    EmailFormatRule,
    NotEmptyRule,
    Rule,
    run_rules,
)

__all__ = [
    "AllowedValuesRule",
    "ColumnMetrics",
    "CustomRule",
    "DomainCount",
    "DuplicateGroup",
    "EmailFormatRule",
    "MissingRow",
    "ModalityCount",
    "NotEmptyRule",
    "ProfileResult",
    "RowIssue",
    "Rule",
    "load_file",
    "profile",
    "render_report",
    "run_rules",
    "write_report",
]
