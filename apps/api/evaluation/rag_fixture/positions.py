from limits import check_concentration, concentration_weight


def position_value(position, price):
    return position["quantity"] * price


def portfolio_value(positions, prices):
    return sum(position_value(position, prices[position["symbol"]]) for position in positions)


def validate_position(position, price, total, ceiling):
    value = position_value(position, price)
    weight = concentration_weight(value, total)
    return check_concentration(weight, ceiling)


def positions_for_symbol(positions, symbol):
    return [position for position in positions if position["symbol"] == symbol]
