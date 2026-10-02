class AssessmentError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 502,
                 reason: str | None = None, question_id: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.reason = reason
        self.question_id = question_id

    def record(self, node: str) -> dict:
        record = {"node": node, "type": self.code, "message": self.message}
        if self.reason:
            record["reason"] = self.reason
        if self.question_id is not None:
            record["question_id"] = self.question_id
        return record
