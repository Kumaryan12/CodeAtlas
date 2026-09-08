from typing import Optional


class AuthService:
    def login(self, email: str, *, remember=False):
        def normalize(value):
            return value.strip()
        return normalize(email)


async def logout(user_id, **options):
    return user_id
