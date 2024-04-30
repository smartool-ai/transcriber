# import asyncio TODO: convert to async
import json
import os
from logging import getLogger
from typing import Optional

from src.lib.enums import ClientEnum, PlatformEnum, EventEnum
from src.models.client import AiClient
from src.models.openai import OpenAIClient
from src.models.dynamo.ticket import SubTicket, TicketModel


import boto3
import botocore


logger = getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
s3 = boto3.resource("s3", region_name=AWS_REGION)
bucket = s3.Bucket(os.environ.get("ARTIST_IMAGES_BUCKET", "dev-transcriptions-ai"))


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
    if event.get("body", "invoke") == "warm":
        logger.debug("Warm event received")
        return
    logger.info("Received event: " + json.dumps(event, indent=2))

    event_type = EventEnum(event.get("event", "TICKET_GENERATION"))
    generation_datetime: str = event.get("generation_datetime")
    number_of_tickets: int = event.get("number_of_tickets", 10)
    document_id: str = event.get("document_id")
    client_str: str = event.get("client", "OPENAI")

    client: AiClient = AiClient(ClientEnum(client_str))

    match event_type:
        case EventEnum.TICKET_GENERATION:
            platform: PlatformEnum = PlatformEnum(event.get("platform", "JIRA"))

            if not document_id:
                raise ValueError("s3_key is required")

            logger.info("Downloading transcript from S3...")
            transcript: str = download_file_from_s3(document_id)
            logger.info("Transcript downloaded")
            logger.debug(transcript)

            if not transcript:
                raise ValueError("Transcript not found")

            try:
                logger.info("Generating tickets from transcript...")
                original_prompt, completion = client.create_tickets(
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
                    original_prompt=original_prompt,
                )
                ticket_model.save()
                logger.info("Tickets saved to DynamoDB")
            except Exception as e:
                logger.error(e)
                raise e("Error generating tickets from transcript. Please try again.")
        case EventEnum.TICKET_EXPANSION:
            ticket: dict = event.get("ticket")
            sub_ticket_id: str = event.get("sub_ticket_id")
            user_id: str = event.get("user_id")

            try:
                logger.info("Retrieving original prompt from DynamoDB...")
                ticket_model: TicketModel = TicketModel.get(document_id, generation_datetime)

                logger.info("Expanding ticket...")
                sub_ticket_prompt, sub_tickets = client.expand_ticket(
                    original_prompt=ticket_model.original_prompt,
                    ticket=ticket,
                    amount_of_sub_tickets=number_of_tickets
                )
                logger.info("Ticket expanded")
                logger.info(f"Sub-tickets: {sub_tickets}")

                ticket_dict: dict = json.loads(sub_tickets.content)
                logger.info(f"Sub-tickets dict: {ticket_dict}")
                modified_tickets: dict = modify_keys(ticket_dict)
                logger.info(f"Modified tickets: {modified_tickets}")

                logger.info("Saving sub-tickets to DynamoDB...")
                sub_ticket_model: SubTicket = SubTicket.initialize(
                    user_id=user_id,
                    sub_ticket_id=sub_ticket_id,
                    tickets=modified_tickets.get("tickets", []),
                    sub_ticket_prompt=sub_ticket_prompt,
                )
                sub_ticket_model.save()
                logger.info("Sub-tickets saved to DynamoDB")
            except Exception as e:
                logger.error(e)
                raise e("Error expanding ticket. Please try again.")
