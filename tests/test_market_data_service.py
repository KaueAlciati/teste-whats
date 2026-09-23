import unittest
from datetime import datetime, timezone

import httpx

from backend.services.market_data_service import (
    IPCA_URL,
    SAVINGS_URL,
    SELIC_URL,
    TREASURY_API_URL,
    clear_market_cache,
    get_market_analysis,
)


TREASURY_CSV_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/resource/"
    "download/precotaxatesourodireto.csv"
)


class MarketDataServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        clear_market_cache()
        self.calls: list[str] = []

    def tearDown(self) -> None:
        clear_market_cache()

    def test_loads_official_indicators_and_does_not_estimate_cdi(self) -> None:
        with self._client() as client:
            market = get_market_analysis(
                client=client,
                current_time=datetime(2026, 9, 23, 12, tzinfo=timezone.utc),
            )

        self.assertTrue(market.available)
        self.assertEqual(market.selic.value, 13.75)
        self.assertEqual(market.savings.value, 0.67)
        self.assertEqual(market.ipca.value, 4.5)
        self.assertEqual(market.ipca.unit, "% em 12 meses")
        self.assertEqual(market.treasury_selic.title, "Tesouro Selic")
        self.assertEqual(str(market.treasury_selic.maturity_date), "2029-03-01")
        self.assertEqual(market.treasury_selic.selic_spread, 0.05)
        self.assertEqual(market.cdi.status, "unavailable")
        self.assertIsNone(market.cdi.value)
        self.assertIn("não é estimado", market.cdi.message)

    def test_selic_ignores_records_after_the_reference_date(self) -> None:
        with self._client() as client:
            market = get_market_analysis(
                client=client,
                current_time=datetime(2026, 9, 23, 12, tzinfo=timezone.utc),
            )

        self.assertEqual(market.selic.value, 13.75)
        self.assertEqual(market.selic.reference_period, "2026-09-23")

    def test_failure_is_isolated_to_its_indicator(self) -> None:
        with self._client(fail_selic=True) as client:
            market = get_market_analysis(client=client)

        self.assertEqual(market.selic.status, "unavailable")
        self.assertEqual(market.savings.status, "available")
        self.assertEqual(market.ipca.status, "available")
        self.assertEqual(market.treasury_selic.status, "available")
        self.assertTrue(market.available)

    def test_six_hour_cache_avoids_repeated_requests(self) -> None:
        now = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
        with self._client() as client:
            first = get_market_analysis(client=client, current_time=now)
            calls_after_first = len(self.calls)
            second = get_market_analysis(client=client, current_time=now)

        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertEqual(len(self.calls), calls_after_first)

    def _client(self, *, fail_selic: bool = False) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            self.calls.append(url)
            if url.startswith(SELIC_URL):
                if fail_selic:
                    return httpx.Response(503, request=request)
                return httpx.Response(
                    200,
                    request=request,
                    json=[
                        {"data": "22/09/2026", "valor": "13,50"},
                        {"data": "24/09/2026", "valor": "14,00"},
                        {"data": "23/09/2026", "valor": "13,75"},
                    ],
                )
            if url == SAVINGS_URL:
                return httpx.Response(
                    200,
                    request=request,
                    json=[{"data": "23/09/2026", "valor": "0,67"}],
                )
            if url == IPCA_URL:
                return httpx.Response(
                    200,
                    request=request,
                    json=[
                        {"V": "Valor", "D3N": "Mês"},
                        {"V": "4.50", "D3N": "agosto 2026"},
                    ],
                )
            if url == TREASURY_API_URL:
                return httpx.Response(
                    200,
                    request=request,
                    json={
                        "result": {
                            "resources": [
                                {"format": "CSV", "url": TREASURY_CSV_URL}
                            ]
                        }
                    },
                )
            if url == TREASURY_CSV_URL:
                content = (
                    "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha\n"
                    "Tesouro Selic;01/03/2031;23/09/2026;0,10\n"
                    "Tesouro Selic;01/03/2029;23/09/2026;0,05\n"
                    "Tesouro Prefixado;01/01/2030;23/09/2026;12,00\n"
                ).encode("utf-8")
                return httpx.Response(200, request=request, content=content)
            raise AssertionError(f"URL inesperada: {url}")

        return httpx.Client(transport=httpx.MockTransport(handler))


if __name__ == "__main__":
    unittest.main()
