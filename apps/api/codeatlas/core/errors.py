class DomainError(Exception):
    """A safe, user-facing failure. Never pass raw upstream exceptions as messages."""

    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
