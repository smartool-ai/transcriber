import datetime
import enum
import json
import os
from logging import getLogger
from typing import Any, Dict, Optional


import boto3
import botocore
from openai import OpenAI
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from pynamodb.attributes import UnicodeAttribute, UTCDateTimeAttribute
from pynamodb.expressions.condition import Condition
from pynamodb.models import Model


logger = getLogger()
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
s3 = boto3.resource("s3", region_name=AWS_REGION)
bucket = s3.Bucket(os.environ.get("ARTIST_IMAGES_BUCKET", "transcriptions-ai"))


class BaseModel(Model):
    """The shared model underlying all Dynamo models."""

    class Meta:
        region = os.environ.get("AWS_REGION", "us-west-2")
        host = os.environ.get(
            "DYNAMO_ENDPOINT", f"https://dynamodb.{region}.amazonaws.com"
        )

    created_datetime = UTCDateTimeAttribute()

    @classmethod
    def initialize_connection(cls) -> None:
        """Initialize connection and fetch table description, indexes, and attributes.

        By running `initialize_connection` in the global namespace, the initial connection
        and the DescribeTable call get executed when the lambda gets initialized / "warmed"
        up rather than during the actual call. This saves about 150ms every time a new instance
        of the lambda gets started up (usually every few minutes).
        """
        cls.describe_table()
        cls.get_attributes()


class TicketModel(BaseModel):
    """
    Model for storing tickets.

    Args:
        BaseModel (_type_): _description_

    Returns:
        _type_: _description_
    """

    class Meta:
        table_name = "Ticket"
        region = os.getenv("AWS_REGION", "us-west-2")

    document_id = UnicodeAttribute(hash_key=True)
    created_datetime = UnicodeAttribute(range_key=True)
    subject = UnicodeAttribute()
    body = UnicodeAttribute()
    estimation_points = UnicodeAttribute()

    @classmethod
    async def initialize(
        cls,
        document_id: str,
        subject: str,
        body: str,
        estimation_points: str,
    ) -> "TicketModel":
        ticket = TicketModel(
            document_id=document_id,
            created_datetime=datetime.datetime.now(),
            subject=subject,
            body=body,
            estimation_points=estimation_points,
        )

        return ticket

    async def save(
        self,
        condition: Optional[Condition] = None
    ) -> Dict[str, Any]:
        """Save the ticket to DynamoDB."""
        return super().save(condition)

    async def delete(
        self,
        condition: Optional[Condition] = None
    ) -> Dict[str, Any]:
        """Delete the ticket from DynamoDB."""
        return super().delete(condition)

    async def __eq__(self, __value: object) -> bool:
        return super().__eq__(__value)

    async def to_serializable_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "created_datetime": self.created_datetime,
            "subject": self.subject,
            "body": self.body,
            "estimation_points": self.estimation_points,
        }

    async def to_json(self) -> str:
        return json.dumps(await self.to_serializable_dict())


class PlatformEnum(str, enum.Enum):
    """Enum for the platform of the ticket."""
    JIRA = "Jira"
    GITHUB = "GitHub"
    TRELLO = "Trello"
    ASANA = "Asana"  # Add more platforms as needed


class OpenAIClient(OpenAI):
    ticket_prompt_prefix: str = (
        "Given the following transcript from a video call, please create {n} {platform} tickets with the following information in json format:\n\n \
        1. Subject: [Enter the subject of the ticket here]\n \
        2. Body: [Enter the detailed description of the ticket here]\n \
        3. Estimation Points: [Enter the estimation points for the ticket here]\n\n \
        Please note that the subject should be a brief summary of the ticket, the body should contain a detailed description of the work to be done, and the estimation points should be an integer representing the estimated effort required to complete the ticket."
    )

    def __init__(self):
        super().__init__(api_key=os.getenv("OPENAI_API_KEY", "test"))

    def create_tickets(
        self,
        prompt: str,
        number_of_tickets: Optional[int] = 10,
        platform: Optional[PlatformEnum] = PlatformEnum.JIRA,
        **kwargs
    ) -> ChatCompletionMessage:
        ticket_prompt: str = (
            self.ticket_prompt_prefix.format(
                n=number_of_tickets, platform=platform.value
            )
            + prompt  # noqa
        )
        params: dict = {
            "model": "gpt-4-turbo-preview",
            "messages": [{"role": "user", "content": ticket_prompt}],
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
        }
        if kwargs:
            params.update(kwargs)

        response = self.chat.completions.create(**params)
        logger.info(response)
        return response.choices[0].message


def download_file_from_s3(s3_key) -> Optional[str]:
    """Download file and return its contents

    Args:
        s3_key (str): The S3 key of the file to download

    Returns:
        str: The contents of the file
    """
    try:
        obj = s3.Object(bucket.name, s3_key)
        logger.info("Loading file...")
        obj.load()
        logger.info("File loaded")
        return obj.get()["Body"].read().decode("utf-8")
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return None
        else:
            raise


def modify_keys(data: dict) -> dict:
    if isinstance(data, dict):
        return {key.lower().replace(" ", ""): modify_keys(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [modify_keys(item) for item in data]
    else:
        return data


def ticket_generation_handler(event, context):
    """Lambda handler for generating tickets from a transcript"""
    s3_key: str = event.get("s3_key")
    number_of_tickets: int = event.get("number_of_tickets", 10)
    platform: PlatformEnum = PlatformEnum(event.get("platform", "JIRA"))

    if not s3_key:
        raise ValueError("s3_key is required")

    transcript: str = download_file_from_s3(s3_key)

    if not transcript:
        raise ValueError("Transcript not found")

    client = OpenAIClient()
    try:
        logger.info("Generating tickets from transcript...")
        completion: ChatCompletionMessage = client.create_tickets(
            prompt=transcript,
            number_of_tickets=number_of_tickets,
            platform=platform.value
        )

        tickets_dict: dict = json.loads(completion.content)

        logger.info("Tickets generated from transcript")
        modified_tickets = modify_keys(tickets_dict)

        for ticket in modified_tickets:
            ticket_model = TicketModel.initialize(
                document_id=s3_key,
                subject=ticket.get("subject"),
                body=ticket.get("body"),
                estimation_points=ticket.get("estimation_points"),
            )
            ticket_model.save()
    except Exception as e:
        logger.error(e)
        raise e("Error generating tickets from transcript. Please try again.")
