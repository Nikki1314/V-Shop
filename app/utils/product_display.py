"""Product display helpers for localized catalog cards."""

from __future__ import annotations

from app.models.product import Product
from app.services.localization import LocalizationService
from app.utils.html import e


def localized_product_name(product: Product, language: str) -> str:
    return {
        "ru": product.name_ru,
        "en": product.name_en,
        "de": product.name_de,
        "uk": product.name_uk,
    }.get(language, product.name_en)


def localized_product_description(product: Product, language: str) -> str:
    return {
        "ru": product.description_ru,
        "en": product.description_en,
        "de": product.description_de,
        "uk": product.description_uk,
    }.get(language, product.description_en)


def format_product_card(product: Product, i18n: LocalizationService) -> str:
    """Build an HTML caption/body for a product card."""
    language = i18n.language
    return i18n.t(
        "product.card",
        name=e(localized_product_name(product, language)),
        description=e(localized_product_description(product, language)),
        flavor_label=i18n.t("product.flavor"),
        flavor=e(product.flavor),
        volume_label=i18n.t("product.volume"),
        volume=e(product.volume),
        nicotine_label=i18n.t("product.nicotine"),
        nicotine=e(product.nicotine_strength),
        price_label=i18n.t("product.price"),
        price=e(product.price),
    )


def format_admin_product_card(product: Product, i18n: LocalizationService) -> str:
    """Admin product details with status and all languages."""
    status = (
        i18n.t("admin.product_status_active")
        if product.is_active
        else i18n.t("admin.product_status_inactive")
    )
    category_name = product.category.name_ru if product.category is not None else "—"
    subcategory_name = (
        product.subcategory.name_ru if product.subcategory is not None else "—"
    )
    return i18n.t(
        "admin.product_card",
        product_id=product.id,
        status=status,
        name_ru=e(product.name_ru),
        name_en=e(product.name_en),
        name_de=e(product.name_de),
        name_uk=e(product.name_uk),
        description_ru=e(product.description_ru),
        description_en=e(product.description_en),
        description_de=e(product.description_de),
        description_uk=e(product.description_uk),
        category=e(category_name),
        subcategory=e(subcategory_name),
        flavor=e(product.flavor),
        volume=e(product.volume),
        nicotine=e(product.nicotine_strength),
        price=e(product.price),
    )
