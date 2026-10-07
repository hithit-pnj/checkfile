"""Core profiling and consistency checks.

All functions are read-only: they never mutate the DataFrame they receive.
They expect a DataFrame produced by :func:`data_quality.loader.load_file`,
i.e. indexed by source line number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

import pandas as pd

# A valid address is ``local@domain.tld``: one @, no spaces, a dot in the
# domain, and a final extension of at least two letters. Shared with the
# e-mail format rule so a domain is counted only when that rule would accept it.
EMAIL_PATTERN: str = r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}"

# --------------------------------------------------------------------------- #
# Result containers
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RowIssue:
    """A problem located on one line of the source file.

    This is the common currency of the tool: profiling checks and business
    rules both produce ``RowIssue`` objects, and the report groups them by line.
    """

    line: int
    respid: str
    #: Short machine-friendly tag: ``"duplicate"`` or a rule name.
    category: str
    column: str | None
    message: str


@dataclass(frozen=True)
class ModalityCount:
    """One distinct value of a column and how many rows hold it.

    ``value`` is ``None`` for the missing-value bucket, which is reported
    separately so the counts of a column add up to the number of rows.
    """

    value: str | None
    count: int
    pct: float


@dataclass(frozen=True)
class ColumnMetrics:
    """Per-column statistics, including the full frequency of each modality."""

    name: str
    dtype: str
    missing_count: int
    missing_pct: float
    unique_count: int
    modalities: tuple[ModalityCount, ...]


@dataclass(frozen=True)
class DomainCount:
    """How many valid e-mail addresses use one domain (the part after ``@``)."""

    domain: str
    count: int
    pct: float


@dataclass(frozen=True)
class MissingRow:
    """One row with at least one empty cell outside the identity columns.

    Completeness is not a business rule: an empty cell is not necessarily an
    error. ``columns`` lists the empty fields, most incomplete rows first.
    """

    line: int
    respid: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class DuplicateGroup:
    """A set of lines sharing the same values on a group of columns."""

    columns: tuple[str, ...]
    values: tuple[str, ...]
    lines: tuple[int, ...]


@dataclass
class ProfileResult:
    """Everything the profiling step found, ready for the exporter."""

    row_count: int
    columns: list[str]
    respid_column: str
    duplicate_column_groups: list[list[str]]
    #: Identity columns left out of the modality frequency table (names, email, id).
    modality_exclude: list[str] = field(default_factory=list)
    column_metrics: list[ColumnMetrics] = field(default_factory=list)
    constant_columns: list[str] = field(default_factory=list)
    duplicate_groups: list[DuplicateGroup] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)
    email_column: str = ""
    email_domains: list[DomainCount] = field(default_factory=list)
    valid_email_count: int = 0
    skipped_email_count: int = 0
    missing_rows: list[MissingRow] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def resolve_respid_column(frame: pd.DataFrame, respid_column: str | None) -> str:
    """Return the respondent-id column, defaulting to the first column."""
    if respid_column is None:
        return str(frame.columns[0])
    if respid_column not in frame.columns:
        raise ValueError(f"respid column '{respid_column}' not found in file columns")
    return respid_column


def ensure_columns_exist(frame: pd.DataFrame, columns: Sequence[str]) -> None:
    """Raise a clear error if any of ``columns`` is absent from the frame."""
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Column(s) not found in file: {', '.join(missing)}")


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #


def is_valid_email(value: object) -> bool:
    """True when ``value`` matches :data:`EMAIL_PATTERN`. Empty cells are not valid."""
    if pd.isna(value):
        return False
    text = str(value).strip()
    return bool(text) and re.fullmatch(EMAIL_PATTERN, text) is not None


def email_domain(value: object) -> str | None:
    """Domain of a valid address, lower-cased, or ``None`` when the address is not valid."""
    if not is_valid_email(value):
        return None
    return str(value).strip().split("@", 1)[1].lower()


def email_domain_counts(frame: pd.DataFrame, email_column: str) -> tuple[list[DomainCount], int, int]:
    """Frequency of each domain among valid addresses, most frequent first.

    Returns the counts, the number of valid addresses, and the number of rows
    skipped because the address is empty or invalid.
    """
    ensure_columns_exist(frame, [email_column])
    domains = frame[email_column].map(email_domain).dropna()
    valid_count = int(len(domains))
    skipped_count = len(frame) - valid_count
    counts = domains.value_counts()
    found = [
        DomainCount(domain=str(domain), count=int(count), pct=_percentage(int(count), valid_count))
        for domain, count in counts.items()
    ]
    found.sort(key=lambda item: (-item.count, item.domain))
    return found, valid_count, skipped_count


def _percentage(count: int, total: int) -> float:
    return round(100.0 * count / total, 2) if total else 0.0


def _modality_counts(series: pd.Series, total: int) -> tuple[ModalityCount, ...]:
    """Frequency of every distinct value, most frequent first, missing last."""
    counts = series.value_counts(dropna=True)
    modalities = [
        ModalityCount(value=str(value), count=int(count), pct=_percentage(int(count), total))
        for value, count in counts.items()
    ]
    modalities.sort(key=lambda modality: (-modality.count, modality.value or ""))
    missing = int(series.isna().sum())
    if missing:
        modalities.append(ModalityCount(value=None, count=missing, pct=_percentage(missing, total)))
    return tuple(modalities)


def column_metrics(frame: pd.DataFrame) -> list[ColumnMetrics]:
    """Missing count / percentage, distinct count, and full modality frequencies."""
    total = len(frame)
    metrics: list[ColumnMetrics] = []
    for name in frame.columns:
        series = frame[name]
        missing = int(series.isna().sum())
        metrics.append(
            ColumnMetrics(
                name=str(name),
                dtype=str(series.dtype),
                missing_count=missing,
                missing_pct=_percentage(missing, total),
                unique_count=int(series.nunique(dropna=True)),
                modalities=_modality_counts(series, total),
            )
        )
    return metrics


def constant_columns(frame: pd.DataFrame) -> list[str]:
    """Columns holding a single distinct (non-missing) value."""
    return [str(name) for name in frame.columns if frame[name].nunique(dropna=True) == 1]


def _is_blank(value: object) -> bool:
    """True for a missing cell or a string made only of spaces."""
    if pd.isna(value):
        return True
    return str(value).strip() == ""


def find_missing_rows(
    frame: pd.DataFrame,
    respid_column: str,
    exclude: Sequence[str] = (),
) -> list[MissingRow]:
    """Rows with an empty cell outside ``exclude``, most empty columns first.

    ``exclude`` is the identity columns (respid, names, e-mail). An empty
    e-mail stays a business rule; an empty department does not.
    """
    watched = [str(column) for column in frame.columns if column not in set(exclude)]
    respids = frame[respid_column].astype(str)
    found: list[MissingRow] = []
    for line, row in frame.iterrows():
        empty = tuple(column for column in watched if _is_blank(row[column]))
        if empty:
            found.append(MissingRow(line=int(line), respid=respids[line], columns=empty))
    found.sort(key=lambda item: (-len(item.columns), item.line))
    return found


def find_duplicates(frame: pd.DataFrame, column_groups: Sequence[Sequence[str]]) -> list[DuplicateGroup]:
    """Rows sharing identical values on each requested group of columns.

    Rows with a missing value in any column of the group are ignored: two
    employees without an email are not duplicates of each other.
    """
    groups: list[DuplicateGroup] = []
    for columns in column_groups:
        columns = list(columns)
        ensure_columns_exist(frame, columns)
        complete = frame.dropna(subset=columns)
        duplicated = complete[complete.duplicated(subset=columns, keep=False)]
        for values, rows in duplicated.groupby(columns, sort=False):
            groups.append(
                DuplicateGroup(
                    columns=tuple(columns),
                    values=tuple(str(value) for value in values),
                    lines=tuple(int(line) for line in rows.index),
                )
            )
    return groups


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def profile(
    frame: pd.DataFrame,
    respid_column: str | None = None,
    duplicate_column_groups: Sequence[Sequence[str]] = (),
    modality_exclude: Sequence[str] = (),
    email_column: str | None = None,
    missing_exclude: Sequence[str] = (),
) -> ProfileResult:
    """Run every profiling check and translate duplicate rows into issues.

    Args:
        frame: DataFrame indexed by source line number (see ``loader``).
        respid_column: Respondent-id column; defaults to the first column.
        duplicate_column_groups: Column groups to check for duplicate rows.
        modality_exclude: Columns left out of the modality frequency table.
            Identity columns (id, names, email) belong here: their quality is
            checked by duplicate detection instead.
        email_column: Column whose valid addresses are counted by domain.
            ``None`` skips that count.
        missing_exclude: Columns ignored by the completeness list (identity
            columns). Empty cells elsewhere are reported, not treated as errors.
    """
    respid_column = resolve_respid_column(frame, respid_column)
    respids = frame[respid_column].astype(str)

    duplicates = find_duplicates(frame, duplicate_column_groups)
    if email_column is None:
        domains, valid_count, skipped_count = [], 0, 0
    else:
        domains, valid_count, skipped_count = email_domain_counts(frame, email_column)

    issues: list[RowIssue] = []
    for group in duplicates:
        key = ", ".join(f"{column}='{value}'" for column, value in zip(group.columns, group.values))
        for line in group.lines:
            others = ", ".join(str(other) for other in group.lines if other != line)
            issues.append(
                RowIssue(
                    line=line,
                    respid=respids[line],
                    category="duplicate",
                    column=" + ".join(group.columns),
                    message=f"Duplicate of line(s) {others} on {key}",
                )
            )

    return ProfileResult(
        row_count=len(frame),
        columns=[str(column) for column in frame.columns],
        respid_column=respid_column,
        duplicate_column_groups=[list(group) for group in duplicate_column_groups],
        modality_exclude=list(modality_exclude),
        column_metrics=column_metrics(frame),
        constant_columns=constant_columns(frame),
        duplicate_groups=duplicates,
        issues=issues,
        email_column=email_column or "",
        email_domains=domains,
        valid_email_count=valid_count,
        skipped_email_count=skipped_count,
        missing_rows=find_missing_rows(frame, respid_column, missing_exclude),
    )
