import json
import os
import tempfile
from pathlib import Path
from uuid import UUID

from src.utils.errors import AssessmentError


class JsonResultStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def write(self, execution_id: str, result: dict) -> str:
        temporary = None
        try:
            name = str(UUID(execution_id)) + ".json"
            payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                             prefix=".assessment-", suffix=".tmp", delete=False) as output:
                temporary = output.name
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            destination = self.directory / name
            os.replace(temporary, destination)
            return str(destination)
        except (OSError, ValueError, TypeError):
            raise AssessmentError("PERSISTENCE_ERROR", "Não foi possível persistir o resultado JSON.", 500) from None
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
