def search_products(query, products):
    return [product for product in products if query.lower() in product.name.lower()]


def apply_discount(price, percent):
    if not 0 <= percent <= 100:
        raise ValueError("Invalid discount")
    return price * (1 - percent / 100)


def reserve_stock(product, quantity):
    if quantity < 1 or product.stock < quantity:
        raise ValueError("Insufficient stock")
    product.stock -= quantity
