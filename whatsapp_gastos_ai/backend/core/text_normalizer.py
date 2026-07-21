from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_ABBREVIATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bvcs\b", flags=re.IGNORECASE), "vocês"),
    (re.compile(r"\bvc\b", flags=re.IGNORECASE), "você"),
    (re.compile(r"\bpq\b", flags=re.IGNORECASE), "porque"),
    (re.compile(r"\bqto\b", flags=re.IGNORECASE), "quanto"),
    (re.compile(r"\bqt\b", flags=re.IGNORECASE), "quanto"),
    (re.compile(r"\btbm\b", flags=re.IGNORECASE), "também"),
    (re.compile(r"\btb\b", flags=re.IGNORECASE), "também"),
    (re.compile(r"\bhj\b", flags=re.IGNORECASE), "hoje"),
    (re.compile(r"\bpfv\b", flags=re.IGNORECASE), "por favor"),
    (re.compile(r"\bpff\b", flags=re.IGNORECASE), "por favor"),
    (re.compile(r"\bvlw\b", flags=re.IGNORECASE), "valeu"),
    (re.compile(r"\bblz\b", flags=re.IGNORECASE), "beleza"),
    (re.compile(r"\bmsg\b", flags=re.IGNORECASE), "mensagem"),
    (re.compile(r"\brelatorio\b", flags=re.IGNORECASE), "relatório"),
    (re.compile(r"\bgrafica\b", flags=re.IGNORECASE), "gráfica"),
    (re.compile(r"\borcamento\b", flags=re.IGNORECASE), "orçamento"),
    (re.compile(r"\bamanha\b", flags=re.IGNORECASE), "amanhã"),
    (re.compile(r"\bmes\b", flags=re.IGNORECASE), "mês"),
    (re.compile(r"\bn\b", flags=re.IGNORECASE), "não"),
    (re.compile(r"\bs\b", flags=re.IGNORECASE), "sim"),
    (re.compile(r"\bq\b", flags=re.IGNORECASE), "que"),
)


def remove_accents_for_matching(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def expand_common_abbreviations(text: str) -> str:
    expanded = text or ""
    for pattern, replacement in _ABBREVIATIONS:
        expanded = pattern.sub(replacement, expanded)
    return expanded


def normalize_user_text(text: str) -> str:
    clean = (text or "").strip().lower()
    clean = expand_common_abbreviations(clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def matching_text(text: str) -> str:
    return remove_accents_for_matching(normalize_user_text(text))


def extract_period(text: str) -> str | None:
    normalized = matching_text(text)
    if not normalized:
        return None

    current_month_tokens = {
        "esse mes",
        "este mes",
        "desse mes",
        "deste mes",
        "do mes",
        "mes atual",
        "agora",
    }
    previous_month_tokens = {
        "mes passado",
        "ultimo mes",
        "mes anterior",
        "do mes passado",
    }
    current_year_tokens = {
        "esse ano",
        "este ano",
        "desse ano",
        "ano atual",
    }
    if any(token in normalized for token in previous_month_tokens):
        return "previous_month"
    if any(token in normalized for token in current_month_tokens):
        return "current_month"
    if any(token in normalized for token in current_year_tokens):
        return "current_year"
    if any(token in normalized for token in {"hoje", "hj", "de hoje"}):
        return "today"
    if "ontem" in normalized:
        return "yesterday"
    if re.search(r"\bde\s+[a-zçãõáéíóú]+\s+a\s+[a-zçãõáéíóú]+\b", normalized):
        return "custom_period"
    if re.search(r"\b\d{1,2}/\d{1,2}(/\d{2,4})?\b", normalized):
        return "custom_period"
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", normalized):
        return "custom_period"
    if re.search(r"\b(janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b", normalized):
        return "custom_period"
    return None


@dataclass(frozen=True, slots=True)
class TextVariants:
    original: str
    normalized: str
    matching: str


def build_text_variants(text: str) -> TextVariants:
    normalized = normalize_user_text(text)
    return TextVariants(original=text or "", normalized=normalized, matching=remove_accents_for_matching(normalized))
