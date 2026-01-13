from mcp import ClientSession, InitializeResult


class ClientSessionWithInit(ClientSession):
    """A client session that stores the initialization result."""

    initialize_result: InitializeResult | None = None
