import base64
import json

from pydantic_core import ValidationError
from structlog import get_logger

from models.lambda_event import LambdaEvent
from models.response import ResponseObject
from services.event_service import EventService


def handler(event, context):
    logger = get_logger()

    logger.info("Handler called", lambda_event=event)

    # Endpoint handler for ELB health check.
    # https://docs.aws.amazon.com/elasticloadbalancing/latest/application/lambda-functions.html#respond-to-load-balancer
    if event["path"] == "/status":
        return {
            "isBase64Encoded": False,
            "statusCode": 200,
            "statusDescription": "200 OK",
            "body": "Status Ok",
            "headers": {
                "Set-cookie": "cookies",
                "Content-Type": "application/json"
            }
        }

    if event["isBase64Encoded"]:
        event = json.loads(base64.b64decode(event["body"]).decode("utf-8"))
    else:
        event = event["body"]

    try:
        logger.info("Validating event")
        lambda_event = LambdaEvent.model_validate(event)
    except ValidationError as e:
        logger.exception("Invalid event", exception=e, lambda_event=event)
        response = ResponseObject()
        response.add_error(error_msg="Event is invalid")
        return response.format_object()

    logger.info("Executing event handler", lambda_event=lambda_event)
    event_service = EventService()

    response = event_service.run(event=lambda_event)

    return response.format_object()
