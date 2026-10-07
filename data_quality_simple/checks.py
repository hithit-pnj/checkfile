"""What we look at in an employee file, before it is used for statistics or surveys.

build_profile describes the file: fill rates, categories, mail suffixes
(the part after @), constant columns, duplicates, empty cells.
run_rules flags lines that should not be used as-is. An empty cell is not a
rule violation; it is listed in the profile so a breakdown stays readable.
A duplicate is a real problem: that person would be counted twice.

To flag another duplicate, add a tuple of column names to DUPLICATE_GROUPS.
To add a rule, write check_<name>(frame) and append it to RULES.
"""

import re
from dataclasses import dataclass

import pandas as pd

RESPID = "respid"
LAST_NAME = "Last name"
FIRST_NAME = "First name"
EMAIL = "E-mail address"

# Not categories: their quality is the duplicate check, not a frequency table.
IDENTITY = (RESPID, LAST_NAME, FIRST_NAME, EMAIL)

DUPLICATE_GROUPS = (
    (RESPID,),
    (EMAIL,),
    (LAST_NAME, FIRST_NAME),
)

# One @, no spaces, a dot in the domain, an extension of at least two letters.
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")


@dataclass
class Issue:
    """One problem on one line. Duplicates and rules both produce these."""

    line: int
    respid: str
    category: str
    column: str
    message: str


@dataclass
class ColumnStat:
    name: str
    dtype: str
    missing: int
    missing_pct: float
    unique: int
    modalities: list  # (value or None, count, percent); None is the missing bucket, last


@dataclass
class DuplicateGroup:
    columns: tuple
    values: tuple
    lines: tuple


@dataclass
class MissingRow:
    line: int
    respid: str
    columns: tuple


@dataclass
class Profile:
    row_count: int
    columns: list
    stats: list
    email_domains: list  # (suffix, count, percent of valid addresses)
    valid_email_count: int
    skipped_email_count: int
    duplicate_groups: list
    duplicate_issues: list
    missing_rows: list


def percent(count, total):
    return round(100.0 * count / total, 2) if total else 0.0


def is_blank(value):
    if pd.isna(value):
        return True
    return str(value).strip() == ""


def email_suffix(value):
    """Part after @ of a valid address, lower-cased, or None."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not EMAIL_RE.fullmatch(text):
        return None
    return text.split("@", 1)[1].lower()


def email_problem(value):
    """Why the address is invalid, or None when it is empty or acceptable."""
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text == "" or EMAIL_RE.fullmatch(text):
        return None
    if any(character.isspace() for character in text):
        reason = "contains a space"
    elif "@" not in text:
        reason = "no @"
    elif text.count("@") > 1:
        reason = "more than one @"
    else:
        local, domain = text.split("@", 1)
        extension = domain.rsplit(".", 1)[-1] if "." in domain else ""
        if not local:
            reason = "nothing before @"
        elif "." not in domain:
            reason = "no dot in the domain (expected name.tld)"
        elif not domain.split(".", 1)[0]:
            reason = "no domain name before the extension"
        elif len(extension) < 2 or not extension.isalpha():
            reason = f"invalid extension '.{extension}' (expected at least 2 letters)"
        else:
            reason = "does not match local@domain.tld"
    return f"Invalid address '{text}': {reason}"


def column_stats(frame):
    total = len(frame)
    stats = []
    for name in frame.columns:
        series = frame[name]
        counts = series.value_counts(dropna=True)
        modalities = [
            (str(value), int(count), percent(int(count), total))
            for value, count in counts.items()
        ]
        modalities.sort(key=lambda item: (-item[1], item[0]))
        missing = int(series.isna().sum())
        if missing:
            modalities.append((None, missing, percent(missing, total)))
        stats.append(
            ColumnStat(
                name=str(name),
                dtype=str(series.dtype),
                missing=missing,
                missing_pct=percent(missing, total),
                unique=int(series.nunique(dropna=True)),
                modalities=modalities,
            )
        )
    return stats


def email_domains(frame):
    """Count of each mail suffix among valid addresses. Empty and invalid are skipped."""
    suffixes = []
    for value in frame[EMAIL]:
        suffix = email_suffix(value)
        if suffix:
            suffixes.append(suffix)
    valid = len(suffixes)
    counts = pd.Series(suffixes).value_counts() if suffixes else []
    found = [
        (str(suffix), int(count), percent(int(count), valid))
        for suffix, count in counts.items()
    ]
    found.sort(key=lambda item: (-item[1], item[0]))
    return found, valid, len(frame) - valid


def find_duplicate_groups(frame):
    """Rows sharing the same values. An empty cell in the group is ignored:
    two employees without an e-mail are not duplicates of each other.
    """
    found = []
    for columns in DUPLICATE_GROUPS:
        complete = frame.dropna(subset=list(columns))
        duplicated = complete[complete.duplicated(subset=list(columns), keep=False)]
        for key, rows in duplicated.groupby(list(columns), sort=False):
            found.append(
                DuplicateGroup(
                    columns=columns,
                    values=tuple(str(value) for value in key),
                    lines=tuple(int(line) for line in rows.index),
                )
            )
    return found


def duplicate_issues(frame, groups):
    respids = frame[RESPID].astype(str)
    issues = []
    for group in groups:
        key = ", ".join(
            f"{column}='{value}'" for column, value in zip(group.columns, group.values)
        )
        label = " + ".join(group.columns)
        for line in group.lines:
            others = ", ".join(str(other) for other in group.lines if other != line)
            issues.append(
                Issue(
                    line=line,
                    respid=respids[line],
                    category="duplicate",
                    column=label,
                    message=f"Duplicate of line(s) {others} on {key}",
                )
            )
    return issues


def missing_rows(frame):
    """Empty cells outside the identity columns, most incomplete rows first."""
    watched = [column for column in frame.columns if column not in IDENTITY]
    respids = frame[RESPID].astype(str)
    rows = []
    for line, row in frame.iterrows():
        empty = tuple(column for column in watched if is_blank(row[column]))
        if empty:
            rows.append(MissingRow(line=int(line), respid=respids[line], columns=empty))
    rows.sort(key=lambda item: (-len(item.columns), item.line))
    return rows


def build_profile(frame):
    groups = find_duplicate_groups(frame)
    domains, valid, skipped = email_domains(frame)
    return Profile(
        row_count=len(frame),
        columns=list(frame.columns),
        stats=column_stats(frame),
        email_domains=domains,
        valid_email_count=valid,
        skipped_email_count=skipped,
        duplicate_groups=groups,
        duplicate_issues=duplicate_issues(frame, groups),
        missing_rows=missing_rows(frame),
    )


def check_email_format(frame):
    """A filled address must look like local@domain.tld. A blank one is ignored."""
    respids = frame[RESPID].astype(str)
    issues = []
    for line, value in frame[EMAIL].items():
        message = email_problem(value)
        if message:
            issues.append(
                Issue(
                    line=int(line),
                    respid=respids[line],
                    category="email_format",
                    column=EMAIL,
                    message=message,
                )
            )
    return issues


def run_rules(frame):
    issues = []
    for check in RULES:
        issues.extend(check(frame))
    return issues


# Add a rule: define check_<name>(frame) above, then list it here.
RULES = [
    check_email_format,
]
