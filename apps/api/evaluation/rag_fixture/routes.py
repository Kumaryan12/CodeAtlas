from access import require_account, require_role
from audit import append_event
from orders import prepare_order
from reports import account_summary


def submit_draft(user, account, store, quantity, quote, now):
    actor = require_role(user, "advisor")
    require_account(user, account)
    order = prepare_order(quantity, quote, now, 60, account["order_limit"])
    append_event(store, actor, "draft_created", account["id"])
    return order


def get_summary(user, account, positions, prices):
    require_account(user, account)
    return account_summary(account, positions, prices)


def health():
    return {"status": "ok"}


def supported_currencies():
    return ["GBP", "USD", "EUR"]
