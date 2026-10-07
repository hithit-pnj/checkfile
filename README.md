# Employee Data Quality Tool

A small, dependency-light Python tool that profiles an employee data file
(CSV or Excel, one line per employee) and produces a plain-text report telling
an operator **exactly which line (and which respid) has which problem**.

```
email_format (1 row)
  Line 30 (respid 1042): Invalid address 'bonjour': no @
```

---

## Table of contents

1. [Quick start](#1-quick-start)
2. [What the report contains](#2-what-the-report-contains)
3. [Architecture overview](#3-architecture-overview)
4. [Module by module](#4-module-by-module)
5. [The business rule engine](#5-the-business-rule-engine)
6. [Adding a new rule](#6-adding-a-new-rule)
7. [Modifying or configuring existing rules](#7-modifying-or-configuring-existing-rules)
8. [Integrating the tool into another system](#8-integrating-the-tool-into-another-system)
9. [Design conventions and guarantees](#9-design-conventions-and-guarantees)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Quick start

### Install

Python 3.10 or newer is required.

```bash
pip install -r requirements.txt
```

This installs `pandas` (2.x), `openpyxl` (for `.xlsx`) and `xlrd` (for legacy `.xls`).

### Run from the command line

From the project root (the folder containing `data_quality/`):

```bash
# Full check of an employee file. Duplicates on respid, E-mail address
# and Last name + First name are always included.
python -m data_quality.main employeefile.xlsx

# Optional: write elsewhere, pick a sheet, add an extra duplicate group.
python -m data_quality.main employeefile.xlsx ^
    --output report.txt ^
    --respid respid ^
    --sheet 0 ^
    --duplicates department
```

(On macOS/Linux replace `^` with `\` for line continuation.)

| Option                 | Default                        | Meaning                                                                 |
|------------------------|--------------------------------|-------------------------------------------------------------------------|
| `input`                | required                       | `.csv`, `.txt`, `.xlsx`, `.xlsm` or `.xls` file.                        |
| `-o`, `--output`       | `<input>_quality_report.txt`   | Where to write the report.                                              |
| `--respid`             | `respid`                       | Name of the respondent-id column.                                       |
| `--sheet`              | `0`                            | Excel sheet name or zero-based index.                                   |
| `--duplicates`         | respid, e-mail, last + first name | Extra column group, added to the three groups that are always checked. Repeat for several groups. |

### Run from Python

```python
from data_quality import load_file, profile, run_rules, write_report, EmailFormatRule

frame = load_file("employees.xlsx")
result = profile(frame, duplicate_column_groups=[["email"], ["last_name", "first_name"]])
violations = run_rules(frame, [EmailFormatRule("email")])
write_report(result, violations, source="employees.xlsx", output_path="report.txt")
```

---

## 2. What the report contains

The report is a single UTF-8 `.txt` file with a header and eight sections.

| Section                       | Level  | Content                                                                                                 |
|-------------------------------|--------|---------------------------------------------------------------------------------------------------------|
| Header                        | file   | Source path, generation time, row count, respid column, list of columns.                               |
| 1. Column metrics             | column | For each column: pandas dtype, missing count, missing %, number of distinct values.                    |
| 2. Modalities                 | value  | Every distinct value of each categorical column, with its count and percentage of rows. Missing values are listed last as `(missing)`. `respid`, `Last name`, `First name` and `E-mail address` are omitted; those columns are covered by the duplicate check. |
| 3. E-mail domains             | value  | Domain (the part after `@`) of each valid address, with its count and its share of valid addresses. Empty and invalid addresses are skipped. |
| 4. Constant columns           | column | Columns with exactly one distinct non-missing value.                                                    |
| 5. Duplicates                 | group  | For each requested column group, the duplicated values and the lines sharing them.                     |
| 6. Missing values             | row    | Rows with an empty cell outside respid, names and e-mail, most incomplete first. This is an inventory, not a violation: those columns are not declared mandatory. |
| 7. Business rule violations   | rule   | Each rule, then every violating line with its respid and the explanation (the address and why it failed, for emails). |
| 8. Issues by line             | row    | Duplicates and rule violations grouped under `Line N (respid X):`. Missing fields are not repeated here. |

Section 6 lists incomplete rows, with the most empty columns first. Section 7 answers "which rows break this rule?". Section 8 answers "what is wrong on this line?".
Sections 1–5 give the shape of the file.

---

## 3. Architecture overview

```
                 ┌──────────────┐
   file.csv ───▶ │   loader.py  │ ───▶ DataFrame indexed by file line number
   file.xlsx     └──────────────┘                  │
                                                   │
                        ┌──────────────────────────┼──────────────────────────┐
                        ▼                                                     ▼
                ┌──────────────┐                                      ┌──────────────┐
                │  checker.py  │  profiling: metrics, constants,      │   rules.py   │  business rules
                │              │  metrics, constants, duplicates      │              │  (Rule subclasses)
                └──────────────┘                                      └──────────────┘
                        │                                                     │
                        │  ProfileResult                                      │  list[RowIssue]
                        │  (+ list[RowIssue] inside)                          │
                        └──────────────────────────┬──────────────────────────┘
                                                   ▼
                                           ┌──────────────┐
                                           │ exporter.py  │ ───▶ report.txt
                                           └──────────────┘

                                           ┌──────────────┐
                                           │   main.py    │  CLI + rule configuration; wires the four modules
                                           └──────────────┘
```

Three ideas hold the design together.

### 3.1 The DataFrame index is the file line number

`loader.load_file()` returns a DataFrame whose index is **the physical line of
each row in the source file**: the header is line 1, so the first data row is
line 2. Every downstream function simply reads `frame.index` to know which line
it is talking about. Nothing else in the code base keeps track of positions.

### 3.2 `RowIssue` is the single currency for row-level findings

```python
@dataclass(frozen=True)
class RowIssue:
    line: int            # physical line in the file
    respid: str          # value of the respid column on that line
    category: str        # "duplicate", or the rule name
    column: str | None   # column concerned (may be None for cross-column rules)
    message: str         # human-readable explanation
```

The profiling checks (`checker.py`) and the business rules (`rules.py`) both
produce `RowIssue` objects. The exporter does not know or care where an issue
came from; it just groups them by line. This is what lets you add rules without
touching the profiling or reporting code.

### 3.3 Profiling and rules are independent

`checker.profile()` knows nothing about rules. `rules.run_rules()` knows nothing
about profiling. `main.run()` calls both and hands the two results to the
exporter. You can run either half alone.

---

## 4. Module by module

### `loader.py` — file input

| Function                          | Purpose                                                                                         |
|-----------------------------------|-------------------------------------------------------------------------------------------------|
| `load_file(path, sheet, encoding)`| Load CSV (delimiter auto-detected, `,` and `;` both work) or Excel. Strips whitespace from column names. Returns a DataFrame indexed by line number. |

Constants `CSV_EXTENSIONS`, `EXCEL_EXTENSIONS`, `HEADER_LINES` and `FIRST_DATA_LINE`
live here. If one day your files have two header lines, `HEADER_LINES` is the
single place to change.

### `checker.py` — profiling and result containers

Result dataclasses: `RowIssue`, `ColumnMetrics`, `ModalityCount`,
`DuplicateGroup`, `ProfileResult`.

| Function                                                | Purpose                                                                                     |
|---------------------------------------------------------|---------------------------------------------------------------------------------------------|
| `column_metrics(frame)`                                 | Missing count / % and distinct count per column, plus the frequency of each value.         |
| `constant_columns(frame)`                               | Columns with a single distinct value.                                                       |
| `find_duplicates(frame, column_groups)`                 | Rows sharing identical values on a column group. Rows with a missing value in the group are ignored. |
| `profile(frame, respid_column, duplicate_column_groups, modality_exclude)` | Runs everything above and converts duplicates into `RowIssue`s. Returns a `ProfileResult`. |
| `resolve_respid_column(frame, name)`                    | Helper: defaults to the first column, validates the name otherwise.                         |
| `ensure_columns_exist(frame, columns)`                  | Helper: raises a clear `ValueError` listing missing columns.                                |

Each check is a standalone function. `profile()` is only a convenience wrapper;
if the larger system needs just the duplicate detection, call `find_duplicates()` directly.

### `rules.py` — business rule engine

Contains the `Rule` base class, the `run_rules()` engine, and the built-in rules.
Described in detail in [section 5](#5-the-business-rule-engine).

### `exporter.py` — report output

| Function                                              | Purpose                                                   |
|-------------------------------------------------------|-----------------------------------------------------------|
| `render_report(profile, violations, source) -> str`   | Build the full report as a string (useful for tests/logs).|
| `write_report(profile, violations, source, output_path) -> Path` | Render and write to disk in UTF-8.             |

Each report section is a private `_xxx()` function returning a list of lines.
To add a section, write one more such function and append it to the `sections`
list in `render_report()`. To change the layout of an existing section, edit
only its function.

### `main.py` — CLI and configuration

| Function          | Purpose                                                                                  |
|-------------------|------------------------------------------------------------------------------------------|
| `build_rules()`   | **The list of business rules applied to every file.** This is the file you edit most.     |
| `run(...)`        | Programmatic entry point: load → profile → rules → write report. Returns the report path. |
| `main(argv)`      | Parses CLI arguments and calls `run()`.                                                  |

---

## 5. The business rule engine

### 5.1 The contract

A rule is a class deriving from `Rule` with three attributes and one method:

```python
class Rule(ABC):
    name: str                 # short identifier, shown as [name] in the report
    column: str | None = None # main column concerned, shown as (column) in the report
    message: str              # human explanation of a violation

    @abstractmethod
    def violations(self, frame: pd.DataFrame) -> pd.Series:
        """Return a boolean Series aligned with frame.index. True = violating row."""
```

That is the whole contract. A rule does **not** build messages per row, does
not look up respids, does not know about line numbers. It only answers the
question "which rows break this rule?" with a boolean mask.

### 5.2 What the engine does

```python
def run_rules(frame, rules, respid_column=None) -> list[RowIssue]
```

For each rule:

1. Calls `rule.violations(frame)`.
2. Re-aligns the mask on `frame.index` (so a rule may return a mask on a
   filtered subset and the engine fills the rest with `False`).
3. For each `True` row, creates a `RowIssue`. The message is `rule.message`, unless the rule implements `detail()` (as `EmailFormatRule` does) to explain that specific row.
4. If the rule raises `KeyError` (a column that does not exist in the file),
   re-raises it as a `ValueError` naming the rule, so the operator knows which
   rule to fix.

### 5.3 Built-in rules

| Class                                                        | Flags rows where…                                                     |
|--------------------------------------------------------------|-----------------------------------------------------------------------|
| `EmailFormatRule(column="email")`                            | the value is present but is not `local@domain.tld`. The report quotes the address and the reason (no `@`, a space, no dot, extension too short, ...). |
| `NotEmptyRule(column)`                                       | the value is missing or a blank string. Not used by default: an empty cell is not a violation unless you add this rule for a column that really is mandatory. |
| `AllowedValuesRule(column, allowed)`                         | the value is present but not in the `allowed` set.                    |
| `CustomRule(name, message, predicate, column=None)`          | `predicate(frame)` returns `True`. For one-off checks without a class.|

### 5.4 Two conventions worth respecting

**Do not flag missing values unless the rule is about missing values.**
`EmailFormatRule` ignores empty cells; `NotEmptyRule` reports them. Otherwise
one empty email would produce two issues on the same line. The idiom is:

```python
values = frame[self.column]
return values.notna() & <condition on values>
```

**Never mutate the frame.** Convert on local copies:

```python
age = pd.to_numeric(frame["age"], errors="coerce")   # fine: new Series
frame["age"] = pd.to_numeric(frame["age"])            # never do this
```

---

## 6. Adding a new rule

### 6.1 The quick way: `CustomRule` with a lambda

For a check you need once, add it directly to `build_rules()` in `main.py`:

```python
from .rules import CustomRule
import pandas as pd

def build_rules() -> list[Rule]:
    return [
        EmailFormatRule("email"),
        CustomRule(
            name="salary_positive",
            message="Salary must be strictly positive",
            predicate=lambda df: pd.to_numeric(df["salary"], errors="coerce") <= 0,
            column="salary",
        ),
    ]
```

### 6.2 The clean way: a `Rule` subclass

For anything reusable or parameterised, write a class in `rules.py` (or in your
own module; nothing forces built-ins and custom rules to live together).

**Example 1 — a single-column rule: hire date not in the future**

```python
class HireDateNotFutureRule(Rule):
    """Hire date must not be after today."""

    name = "hire_date_future"

    def __init__(self, column: str = "hire_date") -> None:
        self.column = column
        self.message = f"'{column}' is in the future"

    def violations(self, frame: pd.DataFrame) -> pd.Series:
        dates = pd.to_datetime(frame[self.column], errors="coerce")
        return dates.notna() & (dates > pd.Timestamp.today())
```

**Example 2 — a cross-column rule: managers must have a team size**

```python
class ManagerHasTeamRule(Rule):
    """Rows flagged as manager must have a strictly positive team_size."""

    name = "manager_team_size"

    def __init__(self, role_column: str = "role", team_column: str = "team_size") -> None:
        self.column = team_column
        self.role_column = role_column
        self.team_column = team_column
        self.message = f"'{role_column}' is Manager but '{team_column}' is empty or zero"

    def violations(self, frame: pd.DataFrame) -> pd.Series:
        is_manager = frame[self.role_column].astype(str).str.strip().str.lower() == "manager"
        team_size = pd.to_numeric(frame[self.team_column], errors="coerce").fillna(0)
        return is_manager & (team_size <= 0)
```

**Example 3 — a rule comparing against a reference list**

```python
class KnownDepartmentRule(Rule):
    """Department must exist in the HR referential."""

    name = "known_department"

    def __init__(self, column: str, referential: Iterable[str]) -> None:
        self.column = column
        self.referential = {value.strip().lower() for value in referential}
        self.message = f"'{column}' not found in the HR department referential"

    def violations(self, frame: pd.DataFrame) -> pd.Series:
        values = frame[self.column]
        normalised = values.astype(str).str.strip().str.lower()
        return values.notna() & ~normalised.isin(self.referential)
```

Then register it:

```python
def build_rules() -> list[Rule]:
    return [
        EmailFormatRule("email"),
        HireDateNotFutureRule("hire_date"),
        ManagerHasTeamRule(),
        KnownDepartmentRule("department", referential=load_departments_from_db()),
    ]
```

### 6.3 Checklist for a new rule

- `name` is short, lowercase, snake_case, unique across rules (it appears in the
  report summary and as `category` on each `RowIssue`).
- `column` is the column the operator should look at first. Use `None` only if
  truly no single column applies.
- `message` reads well after `Line 30 (respid 1042): - [name] (column) ...`.
- `violations()` returns a **boolean** Series indexed like `frame` (or a subset
  of it). Returning strings, integers or a DataFrame will break the engine.
- Missing values are not flagged unless that is the point of the rule.
- The frame is not modified.

### 6.4 Testing a rule in isolation

No test framework is needed to try a rule on a toy frame:

```python
import pandas as pd
from data_quality.rules import EmailFormatRule

df = pd.DataFrame({"email": ["ok@corp.com", "bad@corp", None]})
print(EmailFormatRule("email").violations(df))
# 0    False
# 1     True
# 2    False
```

---

## 7. Modifying or configuring existing rules

### Changing which rules run

Edit `build_rules()` in `main.py`. Comment out or remove what you do not want;
add what you need. Column names must match the file being checked; a rule that
references a column absent from the file stops the run with:

```
ValueError: Rule 'email_format' refers to a column missing from the file: 'email'
```

### Changing a rule's parameters

Built-in rules take their parameters in the constructor:

```python
EmailFormatRule("work_email")                          # different column
AllowedValuesRule("contract", {"CDI", "CDD", "INTERIM"})
```

### Changing a rule's message

Messages are set in `__init__` from the parameters. Edit the f-string there.

### Changing the email pattern

`EMAIL_PATTERN` is a module-level constant in `checker.py` (shared with the domain count). It is intentionally
permissive (`something@something.tld`); tighten it if you need to.

### Running different rule sets for different files

`run()` accepts a `rules=` argument, so the larger system can pass its own list
and ignore `build_rules()` entirely:

```python
from data_quality.main import run

run("site_a.xlsx", rules=rules_for_site_a)
run("site_b.xlsx", rules=rules_for_site_b)
```

---

## 8. Integrating the tool into another system

### Use the high-level entry point

```python
from data_quality.main import run

report_path = run(
    input_path="employees.xlsx",
    output_path="out/employees_report.txt",
    respid_column="respid",
    duplicate_column_groups=[["email"], ["last_name", "first_name"]],
    rules=[EmailFormatRule("email")],
    sheet=0,
)
```

### Or consume the structured results directly

Everything the report shows is available as plain dataclasses before rendering,
which makes it easy to push into a database, a dashboard or a JSON API:

```python
from dataclasses import asdict
from data_quality import load_file, profile, run_rules, EmailFormatRule

frame = load_file("employees.xlsx")
result = profile(frame, duplicate_column_groups=[["email"]])
violations = run_rules(frame, [EmailFormatRule("email")])

all_issues = [*result.issues, *violations]           # list[RowIssue]
issues_as_dicts = [asdict(issue) for issue in all_issues]

for metric in result.column_metrics:                 # list[ColumnMetrics]
    print(metric.name, metric.missing_pct)
```

### Bring your own DataFrame

`profile()` and `run_rules()` only require a DataFrame whose index holds line
numbers. If the data already lives in memory, set that index yourself:

```python
frame = my_dataframe.set_axis(pd.RangeIndex(2, 2 + len(my_dataframe), name="line"))
```

---

## 9. Design conventions and guarantees

- **Read-only.** No function modifies the DataFrame it receives. You can run
  `profile()` and `run_rules()` any number of times on the same frame.
- **Line numbers are physical.** Header on line 1, data from line 2. For CSV
  files this assumes no quoted field spans several lines (rare in employee exports).
- **respid defaults to the column named `respid`.** Override with `respid_column=` / `--respid`.
- **Types are inferred by pandas.** Numeric columns become `int64`/`float64`;
  text becomes `object`. If identifiers with leading zeros must stay text, switch
  `pd.read_csv` / `pd.read_excel` in `loader.py` to `dtype=str`.
- **Duplicates ignore missing values.** Two employees with no email are not duplicates.
- **Errors are loud.** Unknown file type, unknown respid column, unknown
  duplicate column or rule column all raise `ValueError` with the offending name.
  Nothing is silently skipped.
- **Type hints everywhere, PEP 8, English only.**

---

## 10. Troubleshooting

**`ImportError: DLL load failed while importing interval` (Windows)**
Windows application-control policy (Smart App Control / WDAC) blocks the
pandas 3.0 compiled extension on some machines. `requirements.txt` pins
`pandas<3` for that reason; run `pip install -r requirements.txt` again if you
upgraded pandas manually.

**`ValueError: Rule 'xxx' refers to a column missing from the file`**
The rule in `build_rules()` names a column that does not exist in this file.
Check the "Columns" line in the report header (or `frame.columns`) and fix the
rule's column name or remove the rule.

**Line numbers are off by one in Excel**
The loader assumes the header is on row 1. If your sheet has a title row above
the header, remove it or change `HEADER_LINES` in `loader.py`.

**CSV delimiter detected wrongly**
The delimiter is sniffed by pandas' Python engine. If a file defeats the
sniffer, pass an explicit `sep=` to `pd.read_csv` in `loader.py`.
