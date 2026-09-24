import calendar
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta


MONTH_NAMES = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
MONTH_LABELS = {value: key for key, value in MONTH_NAMES.items()}


@dataclass(frozen=True)
class NaturalPeriod:
    start_date: date | None
    end_date: date | None
    key: str
    label: str


def normalize_language(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold().strip())
    without_accents = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return " ".join(
        "".join(
            character if character.isalnum() else " "
            for character in without_accents
        ).split()
    )


def resolve_natural_period(
    text: str,
    *,
    current_date: date,
    period_hint: str | None = None,
    month_hint: int | None = None,
    default: str = "all",
) -> NaturalPeriod:
    normalized = normalize_language(text)
    key, month = _period_from_text(normalized)
    key = period_hint or key or default
    month = month_hint or month

    if key == "today":
        return NaturalPeriod(current_date, current_date, key, "hoje")
    if key == "yesterday":
        target = current_date - timedelta(days=1)
        return NaturalPeriod(target, target, key, "ontem")
    if key == "day_before_yesterday":
        target = current_date - timedelta(days=2)
        return NaturalPeriod(target, target, key, "anteontem")
    if key == "current_week":
        start = current_date - timedelta(days=current_date.weekday())
        return NaturalPeriod(start, current_date, key, "nesta semana")
    if key == "previous_week":
        end = current_date - timedelta(days=current_date.weekday() + 1)
        return NaturalPeriod(end - timedelta(days=6), end, key, "na semana passada")
    if key == "current_month":
        return NaturalPeriod(
            current_date.replace(day=1),
            current_date,
            key,
            "neste mês",
        )
    if key == "previous_month":
        end = current_date.replace(day=1) - timedelta(days=1)
        return NaturalPeriod(end.replace(day=1), end, key, "no mês passado")
    if key in {"last_7_days", "last_15_days", "last_30_days"}:
        days = int(key.split("_")[1])
        return NaturalPeriod(
            current_date - timedelta(days=days - 1),
            current_date,
            key,
            f"nos últimos {days} dias",
        )
    if key == "named_month" and month is not None:
        year = current_date.year if month <= current_date.month else current_date.year - 1
        end = date(year, month, calendar.monthrange(year, month)[1])
        return NaturalPeriod(
            date(year, month, 1),
            end,
            key,
            f"em {MONTH_LABELS[month]}/{year}",
        )
    return NaturalPeriod(None, None, "all", "no período completo")


def _period_from_text(normalized: str) -> tuple[str | None, int | None]:
    if re.search(r"\banteontem\b", normalized):
        return "day_before_yesterday", None
    if re.search(r"\bontem\b", normalized):
        return "yesterday", None
    if re.search(r"\bhoje\b|\bhj\b", normalized):
        return "today", None
    if re.search(r"\bsemana passada\b|\bultima semana\b", normalized):
        return "previous_week", None
    if re.search(r"\b(?:essa|esta|nesta) semana\b", normalized):
        return "current_week", None
    if re.search(r"\bmes passado\b|\bmes anterior\b", normalized):
        return "previous_month", None
    if re.search(r"\b(?:esse|este|neste|deste|desse) mes\b|\bmes atual\b", normalized):
        return "current_month", None
    days_match = re.search(r"\bultimos?\s+(7|15|30)\s+dias\b", normalized)
    if days_match:
        return f"last_{days_match.group(1)}_days", None
    for name, month in MONTH_NAMES.items():
        if re.search(rf"\b{name}\b", normalized):
            return "named_month", month
    return None, None
