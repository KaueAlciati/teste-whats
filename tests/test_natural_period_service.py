import unittest
from datetime import date

from backend.services.natural_period_service import resolve_natural_period


class NaturalPeriodServiceTestCase(unittest.TestCase):
    def test_natural_period_variations(self) -> None:
        current = date(2026, 9, 23)
        cases = (
            ("hoje", date(2026, 9, 23), date(2026, 9, 23)),
            ("qnt gastei hj", date(2026, 9, 23), date(2026, 9, 23)),
            ("ontem", date(2026, 9, 22), date(2026, 9, 22)),
            ("anteontem", date(2026, 9, 21), date(2026, 9, 21)),
            ("essa semana", date(2026, 9, 21), date(2026, 9, 23)),
            ("semana passada", date(2026, 9, 14), date(2026, 9, 20)),
            ("esse mês", date(2026, 9, 1), date(2026, 9, 23)),
            ("mês passado", date(2026, 8, 1), date(2026, 8, 31)),
            ("últimos 7 dias", date(2026, 9, 17), date(2026, 9, 23)),
            ("últimos 15 dias", date(2026, 9, 9), date(2026, 9, 23)),
            ("últimos 30 dias", date(2026, 8, 25), date(2026, 9, 23)),
            ("em agosto", date(2026, 8, 1), date(2026, 8, 31)),
            ("no mês de janeiro", date(2026, 1, 1), date(2026, 1, 31)),
            ("em dezembro", date(2026, 12, 1), date(2026, 12, 31)),
            ("quanto gastei dia 21?", date(2026, 9, 21), date(2026, 9, 21)),
            ("quanto gastei no dia 21?", date(2026, 9, 21), date(2026, 9, 21)),
            ("quanto eu gastei dia 18?", date(2026, 9, 18), date(2026, 9, 18)),
            ("recebi quanto dia 18?", date(2026, 9, 18), date(2026, 9, 18)),
            ("quanto gastei em 21/09?", date(2026, 9, 21), date(2026, 9, 21)),
            ("quanto gastei em 21/09/2025?", date(2025, 9, 21), date(2025, 9, 21)),
            ("quanto gastei em 21 de setembro?", date(2026, 9, 21), date(2026, 9, 21)),
            (
                "quanto gastei em 21 de setembro de 2025?",
                date(2025, 9, 21),
                date(2025, 9, 21),
            ),
        )
        for phrase, expected_start, expected_end in cases:
            with self.subTest(phrase=phrase):
                period = resolve_natural_period(phrase, current_date=current)
                self.assertEqual(period.start_date, expected_start)
                self.assertEqual(period.end_date, expected_end)

    def test_impossible_dates_are_rejected(self) -> None:
        current = date(2026, 9, 23)
        for phrase in ("dia 31", "31/09", "29/02/2026", "31 de setembro"):
            with self.subTest(phrase=phrase):
                period = resolve_natural_period(phrase, current_date=current)
                self.assertFalse(period.is_valid)
                self.assertIsNone(period.start_date)
                self.assertIsNone(period.end_date)


if __name__ == "__main__":
    unittest.main()
