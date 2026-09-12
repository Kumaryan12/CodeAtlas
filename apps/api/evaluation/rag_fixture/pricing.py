"""Synthetic quotes; no external market data is fetched."""


def validate_quote(quote, now, max_age):
    if now - quote["timestamp"] > max_age or quote["price"] <= 0:
        raise ValueError("Invalid or stale quote")
    return quote["price"]


def order_notional(quantity, price):
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    return quantity * price


def convert_currency(amount, rate):
    if rate <= 0:
        raise ValueError("Rate must be positive")
    return amount * rate


def midpoint(bid, ask):
    if bid > ask:
        raise ValueError("Crossed quote")
    return (bid + ask) / 2
