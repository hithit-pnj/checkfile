"""Pre-check an employee file before it is used for statistics or surveys.

    python -m data_quality_simple.main employeefile.xlsx

Or drop the file on verifier.bat. The report is written next to the file. Every check runs
every time. What is checked lives in checks.py; the wording of the log lives
in report.py.
"""

import sys
from pathlib import Path

import pandas as pd

from data_quality_simple.checks import (
    EMAIL,
    FIRST_NAME,
    LAST_NAME,
    RESPID,
    build_profile,
    run_rules,
)
from data_quality_simple.report import render_report

ACCEPTED = {".csv", ".txt", ".xlsx", ".xlsm", ".xls"}


def load_file(path):
    """CSV (comma or semicolon) or Excel, first sheet.

    The index is the line number in the file: header on line 1, first employee
    on line 2.
    """
    path = Path(path)
    if path.suffix.lower() in (".csv", ".txt"):
        frame = pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    else:
        frame = pd.read_excel(path)
    frame.columns = [str(column).strip() for column in frame.columns]
    frame.index = range(2, 2 + len(frame))
    return frame


def main():
    if len(sys.argv) < 2:
        print("Indiquez un fichier Excel ou CSV.")
        print("Vous pouvez aussi le glisser sur verifier.bat.")
        sys.exit(1)
    path = Path(sys.argv[1])
    if path.suffix.lower() not in ACCEPTED:
        print(f"Format non reconnu ({path.suffix}). Utilisez un .xlsx ou un .csv.")
        sys.exit(1)
    frame = load_file(path)
    missing = [name for name in (RESPID, LAST_NAME, FIRST_NAME, EMAIL) if name not in frame.columns]
    if missing:
        print("Colonnes attendues et absentes du fichier : " + ", ".join(missing))
        print("Colonnes trouvees : " + ", ".join(str(column) for column in frame.columns))
        sys.exit(1)
    report_path = path.with_name(f"{path.stem}_quality_report.txt")
    text = render_report(path, build_profile(frame), run_rules(frame))
    report_path.write_text(text, encoding="utf-8")
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
