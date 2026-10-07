"""Write a coding workbook: one sheet per column, modalities and codes.

Identity columns are left out. Empty cells are left out. Nothing is merged:
"France", "france" and " France " stay three modalities. Each sheet numbers
its codes from 1, in alphabetical order. The quality check is a separate tool
and is not imported here.

    python -m coding.generate_coding employeefile.xlsx

The workbook is written next to the file, with the suffix _coding.xlsx.
"""

import sys
from pathlib import Path

import pandas as pd

# Same headers as the employee file. Excluded from coding; not read from the checker.
EXCLUDED = ("respid", "Last name", "First name", "E-mail address")

ACCEPTED = {".csv", ".txt", ".xlsx", ".xlsm", ".xls"}

# Excel sheet names: 31 characters, and none of these.
INVALID_SHEET_CHARS = set("\\/*?:[]")
SHEET_NAME_LIMIT = 31


def load_file(path):
    """CSV (comma or semicolon) or Excel, first sheet. Header spaces are stripped.

    Values inside the file are kept as they are, including surrounding spaces.
    """
    path = Path(path)
    if path.suffix.lower() in (".csv", ".txt"):
        frame = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    else:
        frame = pd.read_excel(path)
    frame.columns = [str(column).strip() for column in frame.columns]
    return frame


def is_blank(value):
    if pd.isna(value):
        return True
    return isinstance(value, str) and value.strip() == ""


def distinct_values(series):
    """Non-empty values, once each, alphabetical. Spelling and spaces are kept."""
    found = []
    seen = set()
    for value in series.tolist():
        if is_blank(value):
            continue
        key = value if isinstance(value, str) else (type(value), str(value))
        if key in seen:
            continue
        seen.add(key)
        found.append(value)
    found.sort(key=lambda value: (str(value).casefold(), str(value)))
    return found


def sheet_problem(name):
    """Why this header cannot be an Excel sheet name, or None when it can."""
    if not name:
        return "en-tete vide"
    if len(name) > SHEET_NAME_LIMIT:
        return f"plus de {SHEET_NAME_LIMIT} caracteres"
    forbidden = "".join(sorted(char for char in INVALID_SHEET_CHARS if char in name))
    if forbidden:
        return f"caractere interdit pour un onglet ({forbidden})"
    return None


def columns_to_code(frame):
    """Column names in file order, without the identity columns."""
    return [name for name in frame.columns if name not in EXCLUDED]


def check_sheet_names(columns):
    """Messages for names Excel would refuse or could not tell apart."""
    problems = []
    for name in columns:
        reason = sheet_problem(name)
        if reason:
            problems.append(f"  {name!r} : {reason}")
    folded = {}
    for name in columns:
        if sheet_problem(name):
            continue
        folded.setdefault(name.casefold(), []).append(name)
    for names in folded.values():
        if len(names) > 1:
            listed = ", ".join(repr(name) for name in names)
            problems.append(f"  onglets identiques pour Excel : {listed}")
    return problems


def write_coding(frame, output_path):
    """One sheet per column. Column A has no header. Codes are under VALUE, from 1."""
    columns = columns_to_code(frame)
    problems = check_sheet_names(columns)
    if problems:
        raise ValueError("En-tetes incompatibles avec un onglet Excel :\n" + "\n".join(problems))
    if not columns:
        raise ValueError("Aucune colonne a coder une fois l'identite et l'e-mail retires.")

    output_path = Path(output_path)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name in columns:
            values = distinct_values(frame[name])
            table = pd.DataFrame({"": values, "VALUE": list(range(1, len(values) + 1))})
            table.to_excel(writer, sheet_name=name, index=False)
            worksheet = writer.sheets[name]
            worksheet["A1"].value = None
            worksheet.column_dimensions["A"].width = 42
            worksheet.column_dimensions["B"].width = 12
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            for cell in worksheet["B"][1:]:
                cell.number_format = "0"
    return output_path


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        print("Indiquez un fichier Excel ou CSV.")
        print("Vous pouvez aussi le glisser sur coding\\generer.bat.")
        return 1
    path = Path(argv[0])
    if path.suffix.lower() not in ACCEPTED:
        print(f"Format non reconnu ({path.suffix}). Utilisez un .xlsx ou un .csv.")
        return 1
    if not path.is_file():
        print(f"Fichier introuvable : {path}")
        return 1
    try:
        frame = load_file(path)
    except Exception as error:
        print(f"Lecture impossible : {error}")
        return 1
    output_path = path.with_name(f"{path.stem}_coding.xlsx")
    try:
        write_coding(frame, output_path)
    except ValueError as error:
        print(error)
        return 1
    except PermissionError:
        print(f"Impossible d'ecrire {output_path}. Fermez le classeur s'il est ouvert.")
        return 1
    except Exception as error:
        print(f"Ecriture impossible : {error}")
        return 1
    print(f"Classeur ecrit : {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
