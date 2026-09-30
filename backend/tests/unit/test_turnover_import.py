from decimal import Decimal

from tender_intel.application.services.turnover_import_service import TurnoverImportService


class _UnusedTextExtractor:
    def extract_text(self, content: bytes) -> str:
        return ""


def test_certificate_table_maps_each_year_to_the_corresponding_amount():
    service = TurnoverImportService(text_extractor=_UnusedTextExtractor())
    text = """Annual turnover for the last three financial years
2022-23 2023-24 2024-25
201671328/- 57,35,60,993/- 63,04,49,219/-
"""

    records = service._extract_text_pairs(text, "certificate.pdf")

    assert [(record.financial_year, record.contractual_turnover) for record in records] == [
        ("2022-23", Decimal("201671328")),
        ("2023-24", Decimal("573560993")),
        ("2024-25", Decimal("630449219")),
    ]
