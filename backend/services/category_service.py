import unicodedata
from difflib import SequenceMatcher

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
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


def find_matching_existing_category(
    db: Session,
    *,
    user_id: int,
    category_name: str,
    transaction_type: str,
    threshold: float = 0.86,
    ambiguity_margin: float = 0.08,
) -> Category | None:
    requested_name = _normalize_category_name(category_name)
    if not requested_name:
        return None
    categories = _available_categories(
        db,
        user_id=user_id,
        transaction_type=transaction_type,
    )
    exact = [
        category
        for category in categories
        if _normalize_category_name(category.name) == requested_name
    ]
    if exact:
        return exact[0]

    ranked = sorted(
        (
            (
                SequenceMatcher(
                    None,
                    requested_name,
                    _normalize_category_name(category.name),
                ).ratio(),
                category,
            )
            for category in categories
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < threshold:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < ambiguity_margin:
        return None
    return ranked[0][1]


def get_or_create_user_category(
    db: Session,
    *,
    user_id: int,
    category_name: str,
    transaction_type: str,
) -> Category:
    normalized_name = " ".join(category_name.strip().split())
    if not normalized_name or len(normalized_name) > 80:
        raise ValueError("Categoria inválida")

    existing = find_existing_category(
        db,
        user_id=user_id,
        category_name=normalized_name,
        transaction_type=transaction_type,
    )
    if existing is not None:
        return existing

    category = Category(
        name=normalized_name,
        type=transaction_type,
        user_id=user_id,
    )
    db.add(category)
    try:
        db.commit()
        db.refresh(category)
        return category
    except IntegrityError:
        db.rollback()
        existing = find_existing_category(
            db,
            user_id=user_id,
            category_name=normalized_name,
            transaction_type=transaction_type,
        )
        if existing is not None:
            return existing
        raise


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
