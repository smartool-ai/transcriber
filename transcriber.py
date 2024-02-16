import enum
import json
import os
from logging import getLogger
from typing import Any, Dict, List, Optional


import boto3
import botocore
from openai import OpenAI
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from pynamodb.attributes import (
    ListAttribute,
    MapAttribute,
    NumberAttribute,
    UnicodeAttribute,
    UTCDateTimeAttribute,
)
from pynamodb.expressions.condition import Condition
from pynamodb.models import Model


logger = getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
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


class TicketModel(MapAttribute):
    subject = UnicodeAttribute()
    body = UnicodeAttribute()
    estimationpoints = NumberAttribute()

    def to_serializable_dict(self) -> dict:
        return {
            "subject": self.subject,
            "body": self.body,
            "estimationpoints": self.estimationpoints,
        }


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
    tickets = ListAttribute(of=TicketModel)

    @classmethod
    def initialize(
        cls, document_id: str, created_datetime: str, tickets: List[dict]
    ) -> "TicketModel":
        ticket = TicketModel(
            document_id=document_id, created_datetime=created_datetime, tickets=tickets
        )

        return ticket

    def save(self, condition: Optional[Condition] = None) -> Dict[str, Any]:
        """Save the ticket to DynamoDB."""
        return super().save(condition)

    def delete(self, condition: Optional[Condition] = None) -> Dict[str, Any]:
        """Delete the ticket from DynamoDB."""
        return super().delete(condition)

    def __eq__(self, __value: object) -> bool:
        return super().__eq__(__value)

    def to_serializable_dict(self) -> dict:
        return {
            "document_id": self.document_id,
            "created_datetime": self.created_datetime,
            "tickets": (
                [ticket.to_serializable_dict() for ticket in self.tickets]
                if self.tickets
                else []
            ),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_serializable_dict())


class PlatformEnum(str, enum.Enum):
    """Enum for the platform of the ticket."""

    JIRA = "JIRA"
    GITHUB = "GITHUB"
    TRELLO = "TRELLO"
    ASANA = "ASANA"  # Add more platforms as needed


class OpenAIClient(OpenAI):
    ticket_prompt_prefix: str = (
        "Given the following transcript from a video call, please create {n} {platform} tickets with the following information in json format:\n\n \
        1. Subject: [Enter the subject of the ticket here]\n \
        2. Body: [Enter the detailed description of the ticket here]\n \
        3. EstimationPoints: [Enter the estimation points for the ticket here]\n\n \
        Please note that the subject should be a brief summary of the ticket, the body should contain a detailed description of the work to be done, and the estimation points should be an integer representing the estimated effort required to complete the ticket."
    )

    def __init__(self):
        super().__init__(api_key=os.getenv("OPENAI_API_KEY", "test"))

    def create_tickets(
        self,
        prompt: str,
        number_of_tickets: Optional[int] = 10,
        platform: Optional[PlatformEnum] = PlatformEnum.JIRA,
        **kwargs,
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
        logger.info("Loading file...")
        obj = s3.Object(bucket.name, s3_key)
        obj.load()
        logger.info("File loaded")
        document = obj.get()
        logger.debug(f"Document: {document}")
        document_read = document["Body"].read()
        logger.debug(f"Document read: {document_read}")
        document_decoded: str = document_read.decode("utf-8")
        logger.debug(f"Document decoded: {document_decoded}")

        if not document_decoded:
            logger.error(f"The file {s3_key} is empty.")
            return None

        return document_decoded
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            logger.error(f"The object {s3_key} does not exist.")
            return None
        else:
            logger.error(f"An error occurred while loading the file: {e}")
            raise


def modify_keys(data: dict) -> dict:
    if isinstance(data, dict):
        return {
            key.lower().replace(" ", ""): modify_keys(value)
            for key, value in data.items()
        }
    elif isinstance(data, list):
        return [modify_keys(item) for item in data]
    else:
        return data


def ticket_generation_handler(event, _):
    """Lambda handler for generating tickets from a transcript"""
    logger.info("Received event: " + json.dumps(event, indent=2))
    document_id: str = event.get("document_id")
    number_of_tickets: int = event.get("number_of_tickets", 10)
    platform: PlatformEnum = PlatformEnum(event.get("platform", "JIRA"))
    generation_datetime: str = event.get("generation_datetime")

    if not document_id:
        raise ValueError("s3_key is required")

    logger.info("Downloading transcript from S3...")
    transcript: str = download_file_from_s3(document_id)
    logger.info("Transcript downloaded")
    logger.debug(transcript)

    if not transcript:
        raise ValueError("Transcript not found")

    client = OpenAIClient()
    try:
        logger.info("Generating tickets from transcript...")
        completion: ChatCompletionMessage = client.create_tickets(
            prompt=transcript, number_of_tickets=number_of_tickets, platform=platform
        )

        tickets_dict: dict = json.loads(completion.content)

        logger.info("Tickets generated from transcript")
        modified_tickets: dict = modify_keys(tickets_dict)
        logger.info(f"Modified tickets: {modified_tickets}")

        logger.info("Saving tickets to DynamoDB...")
        ticket_model: TicketModel = TicketModel.initialize(
            created_datetime=generation_datetime,
            document_id=document_id,
            tickets=modified_tickets.get("tickets", []),
        )
        ticket_model.save()
        logger.info("Tickets saved to DynamoDB")
    except Exception as e:
        logger.error(e)
        raise e("Error generating tickets from transcript. Please try again.")
