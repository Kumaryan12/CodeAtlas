import auth


def sign_in(email, password, users, hasher):
    return auth.login(email, password, users, hasher)


def sign_out(session_id, sessions):
    auth.logout(session_id, sessions)
