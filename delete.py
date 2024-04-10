from src.models.anthro import AnthropicClient


if __name__ == "__main__":
    try:
        client = AnthropicClient()
        client.create_tickets("This is a test prompt")
        client.expand_ticket("This is a test prompt", {"ticket": "test"})
    except Exception as e:
        print(e)
