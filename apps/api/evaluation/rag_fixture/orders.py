from limits import check_order_limit
from pricing import order_notional, validate_quote


def prepare_order(quantity, quote, now, max_age, limit):
    price = validate_quote(quote, now, max_age)
    notional = order_notional(quantity, price)
    check_order_limit(notional, limit)
    return {"quantity": quantity, "price": price, "notional": notional, "status": "draft"}


def cancel_order(order):
    if order["status"] != "draft":
        raise ValueError("Only drafts can be cancelled")
    return {**order, "status": "cancelled"}


def find_order(orders, order_id):
    return next((order for order in orders if order["id"] == order_id), None)


def total_open_notional(orders):
    return sum(order["notional"] for order in orders if order["status"] == "draft")
