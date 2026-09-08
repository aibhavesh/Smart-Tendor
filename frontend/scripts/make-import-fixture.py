"""Build the .xlsx fixture used by e2e-crud.mjs.

`/tenders/import` parses uploads with openpyxl, so the fixture has to be a real workbook.
One fresh row plus one deliberate duplicate, so per-row outcomes are exercised.

    python scripts/make-import-fixture.py <out.xlsx> <unique-suffix>
"""

from __future__ import annotations

import sys

from openpyxl import Workbook

out = sys.argv[1] if len(sys.argv) > 1 else "import-fixture.xlsx"
suffix = sys.argv[2] if len(sys.argv) > 2 else "9999"

wb = Workbook()
ws = wb.active
ws.append(["tender_number", "title", "department", "estimated_value"])
ws.append([f"NIT/2026/{suffix}", "Imported drainage works", "Public Works", "2500000.00"])
ws.append(["NIT/2026/0377", "Duplicate of an existing tender", "Public Works", "100000.00"])
wb.save(out)
print(f"wrote {out} (fresh row NIT/2026/{suffix} + duplicate NIT/2026/0377)")
