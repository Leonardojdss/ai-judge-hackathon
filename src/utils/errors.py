class AssessmentError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 502, transient: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.transient = transient

    def record(self, node: str) -> dict:
        return {"node": node, "type": self.code, "message": self.message}
