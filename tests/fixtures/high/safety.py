from pydantic import BaseModel, ConfigDict, Field


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=8000)
    tool: str | None = None


def validate_input(request):
    value = Input.model_validate(request)
    if any(term in value.message.casefold() for term in ("ignore all instructions", "reveal system prompt")):
        raise ValueError("Blocked instruction override")
    return value.message


def validate_output(response):
    value = Output.model_validate(response)
    if value.tool not in {None, "search_catalog"}:
        raise ValueError("Tool not allowed")
    if "PRIVATE KEY" in value.text or "api_key=" in value.text:
        raise ValueError("Sensitive output blocked")
    return value.text
