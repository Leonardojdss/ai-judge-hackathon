import logging

logger = logging.getLogger(__name__)


def get_langfuse_client(settings):
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(public_key=settings.LANGFUSE_PUBLIC_KEY,
                        secret_key=settings.LANGFUSE_SECRET_KEY.get_secret_value(),
                        base_url=settings.LANGFUSE_HOST,
                        # Defense in depth: no prompts, code or results leave via IO.
                        mask=lambda data, **kwargs: "[REDACTED]")
    except Exception:
        logger.warning("Langfuse indisponível; execução continuará com logs locais.")
        return None


def trace_node(client, metadata: dict):
    """Only explicit operational metadata; never attach raw graph callbacks."""
    if client is None:
        return
    try:
        with client.start_as_current_observation(name=metadata["node"], as_type="span",
                                                 metadata=metadata):
            pass
    except Exception:
        logger.warning("Falha ao registrar metadados no Langfuse.")
