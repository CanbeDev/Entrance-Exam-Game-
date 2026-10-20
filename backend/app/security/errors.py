class SecurityError(Exception):
    """Safe, stable public error. Never include submitted credentials or driver text."""

    def __init__(self, status: int, code: str, *, retry_after: int | None = None):
        self.status = status
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)
