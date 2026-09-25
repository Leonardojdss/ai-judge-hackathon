class AssessmentError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 502, reason: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.reason = reason

    def record(self, node: str) -> dict:
        record = {"node": node, "type": self.code, "message": self.message}
        if self.reason:
            record["reason"] = self.reason
        return record
