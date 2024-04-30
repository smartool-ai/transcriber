from typing import Tuple
from anthropic.types.message import Message

from src.models.anthro import AnthropicClient

if __name__ == "__main__":
    try:
        with open("example_transcription.txt", "r") as f:
            prompt = f.read()
        client = AnthropicClient()
        resp: Tuple[str, dict] = client.create_tickets(prompt)
        # client.expand_ticket("This is a test prompt", {"ticket": "test"})
        ticket_prompt, tickets = resp
        print(tickets)
    except Exception as e:
        print(e)
