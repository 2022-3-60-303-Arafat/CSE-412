"""Export the PFB database to an Excel file, one sheet per table.

Usage:
    python export_excel.py            writes PFB_Database.xlsx next to this file

Needs the openpyxl package (pip install openpyxl). The website itself does not.
The database is opened read-only, so this is safe to run while the server is running.
Password hashes and session tokens are replaced with "(hidden)".
"""

import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "instance" / "pfb.sqlite3"
OUTPUT = ROOT / "PFB_Database.xlsx"

HIDDEN_COLUMNS = {"password_hash", "token_hash"}
FONT = Font(name="Arial", size=10)
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", start_color="1F4E78")
MAX_WIDTH = 60


def main():
    if not DATABASE.exists():
        raise SystemExit("No database yet. Run 'python server.py' once first.")
    connection = sqlite3.connect(f"{DATABASE.as_uri()}?mode=ro", uri=True)
    tables = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    workbook = Workbook()
    overview = workbook.active
    overview.title = "Overview"
    overview.append(["Table", "Rows", "Columns"])

    for name in tables:
        cursor = connection.execute(f'SELECT * FROM "{name}"')
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        sheet = workbook.create_sheet(name[:31])
        sheet.append(columns)
        for row in rows:
            sheet.append(["(hidden)" if column in HIDDEN_COLUMNS else value
                          for column, value in zip(columns, row)])
        style(sheet, len(columns), len(rows))
        if rows:
            table = Table(displayName="t_" + name, ref=sheet.dimensions)
            table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
            sheet.add_table(table)
        overview.append([name, len(rows), ", ".join(columns)])
        overview.cell(row=overview.max_row, column=1).hyperlink = f"#'{name[:31]}'!A1"

    style(overview, 3, len(tables))
    for row in overview.iter_rows(min_row=2, max_col=1):
        row[0].font = Font(name="Arial", size=10, color="0563C1", underline="single")
    connection.close()
    workbook.save(OUTPUT)
    print(f"Wrote {OUTPUT} ({len(tables)} tables)")


def style(sheet, column_count, row_count):
    for cell in sheet[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    for index in range(1, column_count + 1):
        longest = len(str(sheet.cell(row=1, column=index).value)) + 3
        for row in range(2, row_count + 2):
            cell = sheet.cell(row=row, column=index)
            cell.font = FONT
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.value is not None:
                longest = max(longest, len(str(cell.value)))
        sheet.column_dimensions[get_column_letter(index)].width = min(longest + 2, MAX_WIDTH)
    sheet.freeze_panes = "A2"


if __name__ == "__main__":
    main()
