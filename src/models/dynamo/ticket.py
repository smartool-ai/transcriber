import datetime
import json
import os
from typing import Any, Dict, List, Optional

from pynamodb.attributes import (
    ListAttribute,
    MapAttribute,
    NumberAttribute,
    UnicodeAttribute,
    UTCDateTimeAttribute,
)
from pynamodb.expressions.condition import Condition
from pynamodb.models import Model


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


class Ticket(MapAttribute):
    subject = UnicodeAttribute()
    body = UnicodeAttribute()
    estimationpoints = NumberAttribute()

    def to_serializable_dict(self) -> dict:
        return {
            "subject": self.subject,
            "body": self.body,
            "estimationpoints": self.estimationpoints,
        }


class SubTicket(BaseModel):
    """
    Sub-ticket model used as an expansion of a higher level ticket. For example, the tech story to a story.
    """

    class Meta:
        table_name = "SubTicket"
        region = os.getenv("AWS_REGION", "us-west-2")

    user_id = UnicodeAttribute(hash_key=True)
    sub_ticket_id = UnicodeAttribute(range_key=True)
    sub_ticket_prompt = UnicodeAttribute()
    tickets = ListAttribute(of=Ticket)

    @classmethod
    def initialize(
        cls, user_id: str, sub_ticket_id: str, sub_ticket_prompt: str, tickets: List[dict]
    ) -> "SubTicket":
        """
        Initialize a new SubTicketModel instance.

        Args:
            user_id (str): The user ID.
            sub_ticket_id (str): The sub-ticket ID.
            sub_ticket_prompt (str): The sub-ticket prompt.
            ticket (Ticket): The ticket object.

        Returns:
            SubTicketModel: The initialized SubTicketModel instance.
        """
        sub_ticket = SubTicket(
            user_id=user_id,
            sub_ticket_id=sub_ticket_id,
            sub_ticket_prompt=sub_ticket_prompt,
            tickets=tickets,
            created_datetime=datetime.datetime.now(),
        )

        return sub_ticket

    def save(self, condition: Optional[Condition] = None) -> Dict[str, Any]:
        """
        Save the sub-ticket to DynamoDB.

        Args:
            condition (Optional[Condition]): The condition for saving the sub-ticket.

        Returns:
            Dict[str, Any]: The result of the save operation.
        """
        return super().save(condition)

    def delete(self, condition: Optional[Condition] = None) -> Dict[str, Any]:
        """
        Delete the sub-ticket from DynamoDB.

        Args:
            condition (Optional[Condition]): The condition for deleting the sub-ticket.

        Returns:
            Dict[str, Any]: The result of the delete operation.
        """
        return super().delete(condition)

    def __eq__(self, __value: object) -> bool:
        """
        Compare the sub-ticket with another value for equality.

        Args:
            __value (object): The value to compare with.

        Returns:
            bool: True if the sub-ticket is equal to the value, False otherwise.
        """
        return super().__eq__(__value)

    def to_serializable_dict(self) -> dict:
        """
        Convert the sub-ticket model to a serializable dictionary.

        Returns:
            dict: The serializable dictionary representation of the sub-ticket model.
        """
        return {
            "user_id": self.user_id,
            "sub_ticket_id": self.sub_ticket_id,
            "sub_ticket_prompt": self.sub_ticket_prompt,
            "ticket": self.tickets.to_serializable_dict(),
        }

    def to_json(self) -> str:
        """
        Convert the sub-ticket model to a JSON string.

        Returns:
            str: The JSON string representation of the sub-ticket model.
        """
        return json.dumps(self.to_serializable_dict())


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
    tickets = ListAttribute(of=Ticket)
    original_prompt = UnicodeAttribute()

    @classmethod
    def initialize(
        cls, document_id: str, created_datetime: str, tickets: List[dict], original_prompt: str
    ) -> "TicketModel":
        ticket = TicketModel(
            document_id=document_id, created_datetime=created_datetime, tickets=tickets, original_prompt=original_prompt
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
            "original_prompt": self.original_prompt,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_serializable_dict())
