from logging import getLogger
from typing import Any

from src.lib.enums import ClientEnum

logger = getLogger()


class AiClient:
    def __init__(self, Client: ClientEnum) -> None:
        try:
            match Client:
                case ClientEnum.OPENAI:
                    from src.models.openai import OpenAIClient
                    self.client = OpenAIClient()
                case ClientEnum.ANTHROPIC:
                    from src.models.anthro import AnthropicClient
                    self.client = AnthropicClient()
        except Exception as e:
            logger.error(f"Error initializing client: {e}")
            raise e

    def create_tickets(self, **kwargs) -> Any:
        try:
            return self.client.create_tickets(**kwargs)
        except Exception as e:
            logger.error(f"Error creating tickets: {e}")
            raise e
        
    def expand_ticket(self, **kwargs) -> Any:
        try:
            return self.client.expand_ticket(**kwargs)
        except Exception as e:
            logger.error(f"Error expanding ticket: {e}")
            raise e
