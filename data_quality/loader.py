"""Load employee data files (CSV or Excel) into a pandas DataFrame.

Convention used by the whole package: the returned DataFrame is indexed by
the *physical line number* of each row in the source file. The header is
line 1, so the first data row is line 2. Every check reports this number so
that an operator can open the file and go straight to the faulty line.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

CSV_EXTENSIONS: frozenset[str] = frozenset({".csv", ".txt"})
EXCEL_EXTENSIONS: frozenset[str] = frozenset({".xlsx", ".xlsm", ".xls"})

HEADER_LINES: int = 1
FIRST_DATA_LINE: int = HEADER_LINES + 1


def load_file(
    path: str | Path,
    sheet: str | int = 0,
    encoding: str = "utf-8-sig",
) -> pd.DataFrame:
    """Load a CSV or Excel file and index it by source line number.

    Args:
        path: Path to a ``.csv``, ``.txt``, ``.xlsx``, ``.xlsm`` or ``.xls`` file.
        sheet: Excel sheet name or zero-based position (ignored for CSV).
        encoding: Text encoding for CSV files. ``utf-8-sig`` transparently
            handles files with or without a UTF-8 BOM.

    Returns:
        A DataFrame whose index (named ``line``) holds the physical line
        number of each row in the source file. Column names are stripped
        of surrounding whitespace.

    Raises:
        ValueError: If the file extension is not supported.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in CSV_EXTENSIONS:
        # sep=None lets pandas sniff the delimiter (',' or ';' are both common).
        frame = pd.read_csv(path, sep=None, engine="python", encoding=encoding)
    elif suffix in EXCEL_EXTENSIONS:
        frame = pd.read_excel(path, sheet_name=sheet)
    else:
        supported = ", ".join(sorted(CSV_EXTENSIONS | EXCEL_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{suffix}'. Supported: {supported}")

    return _normalize(frame)


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with clean column names and a line-number index."""
    line_index = pd.RangeIndex(FIRST_DATA_LINE, FIRST_DATA_LINE + len(frame), name="line")
    clean_columns = [str(column).strip() for column in frame.columns]
    return frame.set_axis(clean_columns, axis="columns").set_axis(line_index, axis="index")
