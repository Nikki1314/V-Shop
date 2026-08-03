"""Shared display labels for city and delivery type."""

from __future__ import annotations

from app.models.enums import CityChoice, DeliveryType
from app.services.localization import LocalizationService

_CITY_I18N_KEYS = {
    CityChoice.BERLIN.value: "city.berlin",
    CityChoice.DELIVERY.value: "city.delivery",
}

_DELIVERY_I18N_KEYS = {
    DeliveryType.PICKUP.value: "checkout.delivery_pickup",
    DeliveryType.COURIER.value: "checkout.delivery_courier",
    DeliveryType.POSTAL.value: "checkout.delivery_postal",
    DeliveryType.SERVICE.value: "checkout.delivery_service",
}

# English labels for manager notifications (admin-facing, not user locale).
_CITY_LABELS_EN = {
    CityChoice.BERLIN.value: "Berlin",
    CityChoice.DELIVERY.value: "Other cities (Delivery)",
}

_DELIVERY_LABELS_EN = {
    DeliveryType.PICKUP.value: "Pickup",
    DeliveryType.COURIER.value: "Courier",
    DeliveryType.POSTAL.value: "Postal Delivery",
    DeliveryType.SERVICE.value: "Delivery Service",
}


def city_label(i18n: LocalizationService, city: CityChoice | str | None) -> str:
    value = city.value if isinstance(city, CityChoice) else city
    if not value:
        return ""
    key = _CITY_I18N_KEYS.get(value)
    return i18n.t(key) if key else str(value)


def delivery_label(i18n: LocalizationService, delivery_type: str | None) -> str:
    if not delivery_type:
        return ""
    key = _DELIVERY_I18N_KEYS.get(delivery_type)
    return i18n.t(key) if key else delivery_type


def city_label_en(city: str | None) -> str:
    if not city:
        return "—"
    return _CITY_LABELS_EN.get(city, city)


def delivery_label_en(delivery_type: str | None) -> str:
    if not delivery_type:
        return "—"
    return _DELIVERY_LABELS_EN.get(delivery_type, delivery_type)
