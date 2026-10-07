"""Extensible business-rule engine.

A rule flags *rows*. To add one, subclass :class:`Rule` and implement
:meth:`Rule.violations`, returning a boolean Series aligned with the
DataFrame index where ``True`` marks a violating row. The engine
(:func:`run_rules`) converts those flags into :class:`RowIssue` objects
with line numbers and respids, so rules never deal with reporting.

Guidelines for rule authors:

* Do not flag missing values unless the rule is specifically about them
  (see :class:`NotEmptyRule`); otherwise an empty cell would be reported twice.
* Never mutate the DataFrame; use ``pd.to_numeric(..., errors="coerce")``
  and similar non-destructive conversions on local copies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Iterable

import pandas as pd

from .checker import RowIssue, is_valid_email, resolve_respid_column


class Rule(ABC):
    """Base class for all business rules."""

    #: Short identifier shown in the report, e.g. ``"email_format"``.
    name: str
    #: Main column the rule is about (used to label the issue). May be ``None``.
    column: str | None = None
    #: Human-readable explanation of a violation.
    message: str

    @abstractmethod
    def violations(self, frame: pd.DataFrame) -> pd.Series:
        """Return a boolean Series: ``True`` for every violating row."""

    def detail(self, frame: pd.DataFrame) -> pd.Series | None:
        """Optional per-row explanation. ``None`` means use :attr:`message` for every row."""
        return None


def run_rules(
    frame: pd.DataFrame,
    rules: Iterable[Rule],
    respid_column: str | None = None,
) -> list[RowIssue]:
    """Apply every rule to the frame and collect violations as row issues."""
    respid_column = resolve_respid_column(frame, respid_column)
    respids = frame[respid_column].astype(str)

    issues: list[RowIssue] = []
    for rule in rules:
        try:
            mask = rule.violations(frame)
        except KeyError as exc:
            raise ValueError(f"Rule '{rule.name}' refers to a column missing from the file: {exc}") from exc
        mask = mask.reindex(frame.index, fill_value=False).astype(bool)
        details = rule.detail(frame)
        for line in frame.index[mask]:
            message = rule.message if details is None else str(details.loc[line])
            issues.append(
                RowIssue(
                    line=int(line),
                    respid=respids[line],
                    category=rule.name,
                    column=rule.column,
                    message=message,
                )
            )
    return issues


# --------------------------------------------------------------------------- #
# Built-in rules
# --------------------------------------------------------------------------- #


def email_problem(value: object) -> str | None:
    """Return why ``value`` is not a valid email, or ``None`` if it is acceptable.

    Missing and blank values return ``None``: emptiness is :class:`NotEmptyRule`'s job.
    """
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text == "" or is_valid_email(value):
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


class EmailFormatRule(Rule):
    """Non-missing values must look like ``local@domain.tld``.

    Accepted: exactly one ``@``, no spaces, some text on both sides, a dot in
    the domain and a final extension of at least two letters (``a@b.co``,
    ``a@b.co.uk``). Empty cells are ignored.
    """

    name = "email_format"

    def __init__(self, column: str = "email") -> None:
        self.column = column
        self.message = f"Invalid email format in '{column}'"

    def violations(self, frame: pd.DataFrame) -> pd.Series:
        return frame[self.column].map(lambda value: email_problem(value) is not None)

    def detail(self, frame: pd.DataFrame) -> pd.Series:
        return frame[self.column].map(lambda value: email_problem(value) or self.message)


class NotEmptyRule(Rule):
    """The column must be filled (missing or blank string is a violation)."""

    name = "not_empty"

    def __init__(self, column: str) -> None:
        self.column = column
        self.message = f"Missing value in required column '{column}'"

    def violations(self, frame: pd.DataFrame) -> pd.Series:
        values = frame[self.column]
        return values.isna() | (values.astype(str).str.strip() == "")


class AllowedValuesRule(Rule):
    """Non-missing values must belong to a closed list of modalities."""

    name = "allowed_values"

    def __init__(self, column: str, allowed: Iterable[str]) -> None:
        self.column = column
        self.allowed = set(allowed)
        self.message = f"Value not in allowed list for '{column}' ({', '.join(sorted(self.allowed))})"

    def violations(self, frame: pd.DataFrame) -> pd.Series:
        values = frame[self.column]
        return values.notna() & ~values.astype(str).isin(self.allowed)


class CustomRule(Rule):
    """Wrap any ``DataFrame -> boolean Series`` callable as a rule.

    Handy for one-off checks that do not deserve a dedicated class::

        CustomRule(
            name="salary_positive",
            message="Salary must be strictly positive",
            predicate=lambda df: pd.to_numeric(df["salary"], errors="coerce") <= 0,
            column="salary",
        )
    """

    def __init__(
        self,
        name: str,
        message: str,
        predicate: Callable[[pd.DataFrame], pd.Series],
        column: str | None = None,
    ) -> None:
        self.name = name
        self.message = message
        self.column = column
        self._predicate = predicate

    def violations(self, frame: pd.DataFrame) -> pd.Series:
        return self._predicate(frame)
