"""Replace modalities with the codes from a coding workbook.

A column with no sheet in the workbook is left unchanged. A value with no
row in its sheet is left unchanged. Empty cells stay empty. Nothing is
merged: the text must match the coding sheet exactly.

    python -m coding.generate_coded_file employeefile.xlsx
    python -m coding.generate_coded_file employeefile.xlsx employeefile_coding.xlsx

The coded copy is written next to the source, with the suffix _coded.xlsx.
The source file is not modified.
"""

import sys
from pathlib import Path

import pandas as pd

from coding.generate_coding import ACCEPTED, is_blank, load_file

VALUE = "VALUE"
# Workbooks generated before the header change.
LEGACY_MODALITY = "modalité"
LEGACY_CODE = "code"
UNKNOWN_LIMIT = 15


def match_key(value):
    """Identity of a cell for an exact lookup.

    Whole numbers match across Excel's int/float round-trip. Strings are
    compared as they are, including spaces and case.
    """
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, int):
        return ("num", str(value))
    if isinstance(value, float):
        if value.is_integer():
            return ("num", str(int(value)))
        return ("num", repr(value))
    if isinstance(value, pd.Timestamp):
        return ("time", value.isoformat())
    return (type(value).__name__, str(value))


def as_code(value):
    """Code written into the copy. Whole numbers stay integers."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, int):
        return int(value)
    return value


def coding_columns(table):
    """Names of the modality column and the code column, or None.

    Current sheets: modalities in column A (header left empty), codes under VALUE.
    Older sheets: headers modalité and code. Pandas names a blank header Unnamed: 0.
    """
    names = [str(column).strip() for column in table.columns]
    table.columns = names
    if VALUE in names:
        modality = names[0]
        if modality == VALUE:
            return None
        return modality, VALUE
    if LEGACY_MODALITY in names and LEGACY_CODE in names:
        return LEGACY_MODALITY, LEGACY_CODE
    return None


def load_coding(path):
    """Sheet name -> {match_key: code}. A sheet without VALUE is skipped."""
    book = pd.read_excel(path, sheet_name=None)
    sheets = {}
    warnings = []
    for name, table in book.items():
        sheet = str(name).strip()
        columns = coding_columns(table)
        if columns is None:
            warnings.append(
                f"Onglet {sheet!r} ignore : les modalites sont en colonne A, les codes sous {VALUE!r}."
            )
            continue
        modality_column, code_column = columns
        lookup = {}
        for modality, code in zip(table[modality_column].tolist(), table[code_column].tolist()):
            if is_blank(modality):
                continue
            if is_blank(code):
                warnings.append(f"Onglet {sheet!r} : modalite {modality!r} sans code, ignoree.")
                continue
            key = match_key(modality)
            stored = as_code(code)
            if key in lookup and lookup[key] != stored:
                warnings.append(
                    f"Onglet {sheet!r} : {modality!r} est en double. Le premier code est garde ({lookup[key]})."
                )
                continue
            lookup[key] = stored
        sheets[sheet] = lookup
    return sheets, warnings


def apply_coding(frame, sheets):
    """Copy of the file. Only columns that have a sheet are translated."""
    coded = frame.copy()
    unchanged = []
    replaced = {}
    unknown = {}
    for name in frame.columns:
        lookup = sheets.get(name)
        if lookup is None:
            unchanged.append(name)
            continue
        values = []
        hits = 0
        missed = {}
        for value in frame[name].tolist():
            if is_blank(value):
                values.append(pd.NA)
                continue
            key = match_key(value)
            if key in lookup:
                values.append(lookup[key])
                hits += 1
            else:
                values.append(value)
                label = repr(value) if isinstance(value, str) else str(value)
                missed[label] = missed.get(label, 0) + 1
        # object keeps integers as integers when the column also has empty cells.
        coded[name] = pd.Series(values, index=frame.index, dtype=object)
        replaced[name] = hits
        if missed:
            unknown[name] = sorted(missed.items(), key=lambda item: (-item[1], item[0]))
    return coded, unchanged, replaced, unknown


def default_coding_path(source):
    return source.with_name(f"{source.stem}_coding.xlsx")


def report(unchanged, replaced, unknown, warnings):
    lines = []
    for warning in warnings:
        lines.append(warning)
    if unchanged:
        lines.append("Colonnes laissees en clair (pas d'onglet) : " + ", ".join(unchanged))
    if not replaced:
        lines.append("Aucune colonne n'a d'onglet dans le classeur de codage.")
    for name, count in replaced.items():
        lines.append(f"{name} : {count} valeur(s) remplacee(s) par un code")
    for name, rows in unknown.items():
        lines.append(f"{name} : modalites sans code, laissees en clair :")
        shown = rows[:UNKNOWN_LIMIT]
        for label, count in shown:
            lines.append(f"  {label} ({count})")
        extra = len(rows) - len(shown)
        if extra:
            lines.append(f"  ... et {extra} autre(s)")
    return "\n".join(lines)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        print("Indiquez le fichier original, et eventuellement le classeur de codage.")
        print("Vous pouvez aussi glisser le fichier original sur coding\\remplacer.bat.")
        return 1
    source = Path(argv[0])
    if source.suffix.lower() not in ACCEPTED:
        print(f"Format non reconnu ({source.suffix}). Utilisez un .xlsx ou un .csv.")
        return 1
    if not source.is_file():
        print(f"Fichier introuvable : {source}")
        return 1
    coding_path = Path(argv[1]) if len(argv) > 1 else default_coding_path(source)
    if not coding_path.is_file():
        print(f"Classeur de codage introuvable : {coding_path}")
        print("Il doit etre a cote du fichier original et se terminer par _coding.xlsx.")
        return 1
    try:
        frame = load_file(source)
        sheets, warnings = load_coding(coding_path)
    except Exception as error:
        print(f"Lecture impossible : {error}")
        return 1
    coded, unchanged, replaced, unknown = apply_coding(frame, sheets)
    output_path = source.with_name(f"{source.stem}_coded.xlsx")
    try:
        coded.to_excel(output_path, index=False, engine="openpyxl")
    except PermissionError:
        print(f"Impossible d'ecrire {output_path}. Fermez le classeur s'il est ouvert.")
        return 1
    except Exception as error:
        print(f"Ecriture impossible : {error}")
        return 1
    text = report(unchanged, replaced, unknown, warnings)
    if text:
        print(text)
    print(f"Fichier code ecrit : {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
