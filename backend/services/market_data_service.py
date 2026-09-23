import csv
import io
import logging
import threading
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx

from backend.schemas.insights import (
    MarketAnalysisState,
    MarketRateIndicator,
    MarketSource,
    TreasurySelicIndicator,
)


logger = logging.getLogger("uvicorn.error")

MARKET_CACHE_TTL = timedelta(hours=6)
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_TREASURY_CSV_BYTES = 25 * 1024 * 1024

SELIC_URL = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/"
    "dados"
)
SAVINGS_URL = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.195/"
    "dados/ultimos/1?formato=json"
)
IPCA_URL = (
    "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/2265/"
    "p/last%201"
)
TREASURY_DATASET_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "taxas-dos-titulos-ofertados-pelo-tesouro-direto"
)
TREASURY_API_URL = (
    "https://www.tesourotransparente.gov.br/ckan/api/3/action/"
    "package_show?id=taxas-dos-titulos-ofertados-pelo-tesouro-direto"
)
B3_DI_SOURCE_URL = (
    "https://www.b3.com.br/pt_br/market-data-e-indices/indices/"
    "indices-de-segmentos-e-setoriais/di/"
    "metodologia-de-apuracao-da-taxa/"
)

_cache_lock = threading.RLock()
_cached_market: MarketAnalysisState | None = None
_cache_expires_at: datetime | None = None


def get_market_analysis(
    *,
    force_refresh: bool = False,
    current_time: datetime | None = None,
    client: httpx.Client | None = None,
) -> MarketAnalysisState:
    global _cached_market, _cache_expires_at

    now = current_time or datetime.now(timezone.utc)
    with _cache_lock:
        if (
            not force_refresh
            and _cached_market is not None
            and _cache_expires_at is not None
            and now < _cache_expires_at
        ):
            return _cached_market.model_copy(update={"cached": True})

        owns_client = client is None
        http_client = client or httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": "FinControlAI/1.0 market-data"},
        )
        try:
            selic = _safe_rate(
                "Selic",
                lambda: _fetch_bcb_rate(
                    http_client,
                    url=SELIC_URL,
                    unit="% a.a.",
                    source_name="Banco Central do Brasil - SGS 432",
                    minimum=Decimal("0"),
                    maximum=Decimal("100"),
                    not_after=now.date(),
                ),
                source=MarketSource(
                    name="Banco Central do Brasil - SGS 432",
                    url=SELIC_URL,
                ),
                unit="% a.a.",
            )
            savings = _safe_rate(
                "Poupança",
                lambda: _fetch_bcb_rate(
                    http_client,
                    url=SAVINGS_URL,
                    unit="% a.m.",
                    source_name="Banco Central do Brasil - SGS 195",
                    minimum=Decimal("-10"),
                    maximum=Decimal("10"),
                ),
                source=MarketSource(
                    name="Banco Central do Brasil - SGS 195",
                    url=SAVINGS_URL,
                ),
                unit="% a.m.",
            )
            ipca = _safe_rate(
                "IPCA",
                lambda: _fetch_ipca(http_client),
                source=MarketSource(
                    name="IBGE/SIDRA - tabela 1737, variável 2265",
                    url=IPCA_URL,
                ),
                unit="% em 12 meses",
            )
            treasury = _safe_treasury(
                lambda: _fetch_treasury_selic(http_client)
            )
        finally:
            if owns_client:
                http_client.close()

        cdi = MarketRateIndicator(
            status="unavailable",
            value=None,
            unit="% a.a.",
            reference_period=None,
            source=MarketSource(
                name="B3 - Taxa DI",
                url=B3_DI_SOURCE_URL,
            ),
            message=(
                "Indisponível: não há uma API HTTP pública e estável da B3 "
                "integrada; o valor não é estimado."
            ),
        )
        available_count = sum(
            indicator.status == "available"
            for indicator in (selic, savings, ipca, treasury)
        )
        market = MarketAnalysisState(
            available=available_count > 0,
            message=(
                "Indicadores oficiais carregados."
                if available_count == 4
                else "Alguns indicadores oficiais estão temporariamente indisponíveis."
            ),
            updated_at=now,
            cached=False,
            selic=selic,
            cdi=cdi,
            ipca=ipca,
            savings=savings,
            treasury_selic=treasury,
        )
        _cached_market = market
        _cache_expires_at = now + MARKET_CACHE_TTL
        return market


def clear_market_cache() -> None:
    global _cached_market, _cache_expires_at
    with _cache_lock:
        _cached_market = None
        _cache_expires_at = None


def _fetch_bcb_rate(
    client: httpx.Client,
    *,
    url: str,
    unit: str,
    source_name: str,
    minimum: Decimal,
    maximum: Decimal,
    not_after: date | None = None,
) -> MarketRateIndicator:
    request_params = None
    if not_after is not None:
        start_date = not_after - timedelta(days=90)
        request_params = {
            "formato": "json",
            "dataInicial": start_date.strftime("%d/%m/%Y"),
            "dataFinal": not_after.strftime("%d/%m/%Y"),
        }
    response = client.get(url, params=request_params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise ValueError("resposta vazia")
    candidates: list[tuple[date, Decimal]] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        try:
            reference = datetime.strptime(record["data"], "%d/%m/%Y").date()
            value = _decimal(record.get("valor"))
        except (KeyError, TypeError, ValueError):
            continue
        if not_after is not None and reference > not_after:
            continue
        if minimum <= value <= maximum:
            candidates.append((reference, value))
    if not candidates:
        raise ValueError("nenhum registro válido na data de referência")
    reference, value = max(candidates, key=lambda item: item[0])
    return MarketRateIndicator(
        status="available",
        value=float(value),
        unit=unit,
        reference_period=reference.isoformat(),
        source=MarketSource(name=source_name, url=str(response.request.url)),
    )


def _fetch_ipca(client: httpx.Client) -> MarketRateIndicator:
    response = client.get(IPCA_URL)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("resposta inválida")
    records = [
        row
        for row in payload
        if isinstance(row, dict)
        and row.get("V") not in {None, "", "Valor", "...", "-"}
    ]
    if not records:
        raise ValueError("resposta vazia")
    record = records[-1]
    value = _decimal(record["V"])
    if not Decimal("-100") <= value <= Decimal("100"):
        raise ValueError("valor fora do intervalo esperado")
    reference = record.get("D3N") or record.get("D3C")
    return MarketRateIndicator(
        status="available",
        value=float(value),
        unit="% em 12 meses",
        reference_period=str(reference) if reference else None,
        source=MarketSource(
            name="IBGE/SIDRA - tabela 1737, variável 2265",
            url=IPCA_URL,
        ),
    )


def _fetch_treasury_selic(client: httpx.Client) -> TreasurySelicIndicator:
    metadata_response = client.get(TREASURY_API_URL)
    metadata_response.raise_for_status()
    metadata = metadata_response.json()
    resources = metadata.get("result", {}).get("resources", [])
    csv_url = next(
        (
            resource.get("url")
            for resource in resources
            if str(resource.get("format", "")).casefold() == "csv"
            and resource.get("url")
        ),
        None,
    )
    if not csv_url or not _is_official_treasury_url(csv_url):
        raise ValueError("recurso CSV oficial ausente")

    csv_response = client.get(csv_url)
    csv_response.raise_for_status()
    if len(csv_response.content) > MAX_TREASURY_CSV_BYTES:
        raise ValueError("arquivo oficial excede o limite de segurança")
    try:
        text = csv_response.content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = csv_response.content.decode("latin-1")

    candidates: list[dict] = []
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    for original in reader:
        row = {_normalize_key(key): value for key, value in original.items()}
        title = (row.get("tipo titulo") or "").strip()
        if "tesouro selic" not in _normalize_key(title):
            continue
        try:
            reference_date = _parse_br_date(row.get("data base"))
            maturity_date = _parse_br_date(row.get("data vencimento"))
            rate = _decimal(row.get("taxa compra manha"))
        except ValueError:
            continue
        candidates.append(
            {
                "title": title,
                "reference_date": reference_date,
                "maturity_date": maturity_date,
                "rate": rate,
            }
        )
    if not candidates:
        raise ValueError("Tesouro Selic não encontrado")
    latest_reference = max(item["reference_date"] for item in candidates)
    latest = [
        item for item in candidates if item["reference_date"] == latest_reference
    ]
    selected = min(latest, key=lambda item: item["maturity_date"])
    return TreasurySelicIndicator(
        status="available",
        title=selected["title"],
        maturity_date=selected["maturity_date"],
        selic_spread=float(selected["rate"]),
        unit="% a.a.",
        reference_period=selected["reference_date"].isoformat(),
        source=MarketSource(
            name="Tesouro Transparente - taxas do Tesouro Direto",
            url=TREASURY_DATASET_URL,
        ),
    )


def _safe_rate(
    label: str,
    fetcher,
    *,
    source: MarketSource,
    unit: str,
) -> MarketRateIndicator:
    try:
        return fetcher()
    except Exception as exc:
        logger.warning(
            "Indicador oficial indisponível: %s; erro=%s",
            label,
            type(exc).__name__,
        )
        return MarketRateIndicator(
            status="unavailable",
            value=None,
            unit=unit,
            reference_period=None,
            source=source,
            message="Fonte oficial temporariamente indisponível.",
        )


def _safe_treasury(fetcher) -> TreasurySelicIndicator:
    source = MarketSource(
        name="Tesouro Transparente - taxas do Tesouro Direto",
        url=TREASURY_DATASET_URL,
    )
    try:
        return fetcher()
    except Exception as exc:
        logger.warning(
            "Indicador oficial indisponível: Tesouro Selic; erro=%s",
            type(exc).__name__,
        )
        return TreasurySelicIndicator(
            status="unavailable",
            title=None,
            maturity_date=None,
            selic_spread=None,
            unit="% a.a.",
            reference_period=None,
            source=source,
            message="Fonte oficial temporariamente indisponível.",
        )


def _decimal(value) -> Decimal:
    if value is None:
        raise ValueError("valor ausente")
    normalized = str(value).strip()
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("valor inválido") from exc


def _parse_br_date(value) -> date:
    if not value:
        raise ValueError("data ausente")
    return datetime.strptime(str(value).strip(), "%d/%m/%Y").date()


def _normalize_key(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return " ".join(
        "".join(char for char in normalized if not unicodedata.combining(char))
        .casefold()
        .split()
    )


def _is_official_treasury_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in {
            "tesourotransparente.gov.br",
            "www.tesourotransparente.gov.br",
        }
    )
