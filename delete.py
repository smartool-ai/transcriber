from anthropic.types.message import Message

from src.models.anthro import AnthropicClient


if __name__ == "__main__":
    try:
        with open("example.txt", "r") as f:
            prompt = f.read()
        client = AnthropicClient()
        resp: Message = client.create_tickets(prompt)
        # client.expand_ticket("This is a test prompt", {"ticket": "test"})
        print(resp)
    except Exception as e:
        print(e)
