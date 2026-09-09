def verify_password(password, stored_hash, hasher):
    """Verify supplied credentials against the stored password digest."""
    return hasher.verify(stored_hash, password)


def login(email, password, users, hasher):
    user = users.find_by_email(email)
    if user is None or not verify_password(password, user.password_hash, hasher):
        raise ValueError("Invalid credentials")
    return {"user_id": user.id}


def logout(session_id, sessions):
    sessions.delete(session_id)
