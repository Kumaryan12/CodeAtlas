import catalog


def checkout(product, quantity, discount):
    catalog.reserve_stock(product, quantity)
    return catalog.apply_discount(product.price, discount) * quantity
