import boto3
import json
import os
import requests


def lambda_handler(event, context):
    # Retrieve the S3 bucket and key from the event
    s3_bucket = event['Records'][0]['s3']['bucket']['name']
    s3_key = event['Records'][0]['s3']['object']['key']

    # Retrieve the text from the S3 object
    s3_client = boto3.client('s3')
    s3_object = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
    text = s3_object['Body'].read().decode('utf-8')

    # Send the text to OpenAI ChatGPT
    # response = send_to_chatgpt(text)

    # Do something with the response (e.g., save to another S3 bucket)
    # ...

    return {
        'statusCode': 200,
        'body': json.dumps('Success')
    }


def send_to_chatgpt(text):
    # Set up the OpenAI ChatGPT API endpoint and headers
    api_endpoint = 'https://api.openai.com/v1/engines/davinci-codex/completions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {os.environ["OPENAI_API_KEY"]}'
    }

    # Prepare the payload for the API request
    payload = {
        'prompt': text,
        'max_tokens': 100,
        'temperature': 0.7
    }

    # Send the request to OpenAI ChatGPT
    response = requests.post(api_endpoint, headers=headers, json=payload)

    # Extract and return the generated text from the response
    return response.json()['choices'][0]['text']
