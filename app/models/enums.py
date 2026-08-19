"""Domain enumerations used by ORM models."""

from enum import StrEnum


class LanguageCode(StrEnum):
    RU = "ru"
    EN = "en"
    DE = "de"
    UK = "uk"


class CityChoice(StrEnum):
    BERLIN = "berlin"
    DELIVERY = "delivery"


class DeliveryType(StrEnum):
    PICKUP = "pickup"
    COURIER = "courier"
    POSTAL = "postal"
    SERVICE = "service"


class PaymentMethod(StrEnum):
    """How the customer prefers to pay. Stored by value on the order."""

    CASH = "cash"
    CARD = "card"


class OrderStatus(StrEnum):
    NEW = "New"
    ACCEPTED = "Accepted"
    SHIPPED = "Shipped"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
