import unicodedata

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.models.category import Category


def _normalize_category_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name.casefold().strip())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def find_category_or_default(
    db: Session,
    *,
    user_id: int,
    category_name: str | None,
    transaction_type: str,
) -> Category:
    categories = _available_categories(
        db,
        user_id=user_id,
        transaction_type=transaction_type,
    )

    requested_name = _normalize_category_name(category_name or "Outros")
    for category in categories:
        if _normalize_category_name(category.name) == requested_name:
            return category

    fallback_name = _normalize_category_name("Outros")
    for category in categories:
        if _normalize_category_name(category.name) == fallback_name:
            return category

    raise LookupError("Categoria padrão não encontrada")


def find_existing_category(
    db: Session,
    *,
    user_id: int,
    category_name: str,
    transaction_type: str,
) -> Category | None:
    requested_name = _normalize_category_name(category_name)
    for category in _available_categories(
        db,
        user_id=user_id,
        transaction_type=transaction_type,
    ):
        if _normalize_category_name(category.name) == requested_name:
            return category
    return None


def _available_categories(
    db: Session,
    *,
    user_id: int,
    transaction_type: str,
) -> list[Category]:
    return list(
        db.scalars(
            select(Category)
            .where(
                Category.type == transaction_type,
                or_(Category.user_id.is_(None), Category.user_id == user_id),
            )
            .order_by(Category.user_id.desc().nulls_last())
        )
    )
