from access import redact_account
from positions import portfolio_value


def account_summary(account, positions, prices):
    return {"account": redact_account(account), "value": portfolio_value(positions, prices)}


def csv_row(values):
    import csv
    import io

    output = io.StringIO()
    csv.writer(output).writerow(values)
    return output.getvalue()


def page_rows(rows, offset, size):
    if offset < 0 or not 1 <= size <= 100:
        raise ValueError("Invalid page")
    return rows[offset : offset + size]


def report_filename(account_id):
    if not account_id.isalnum():
        raise ValueError("Invalid identifier")
    return account_id + ".csv"
