"""Synthetic authorization examples; not a real bank policy."""


def require_role(user, role):
    if role not in user["roles"]:
        raise PermissionError("Role required")
    return user["id"]


def can_view_account(user, account):
    return user["tenant_id"] == account["tenant_id"] and account["id"] in user["account_ids"]


def require_account(user, account):
    if not can_view_account(user, account):
        raise PermissionError("Account access denied")
    return account


def redact_account(account):
    return {
        "id": account["id"],
        "label": account["label"],
        "number": "****" + account["number"][-4:],
    }
