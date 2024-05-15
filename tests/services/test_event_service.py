from typing import List

from structlog.testing import capture_logs

from models.jobs import BackgroundJob, CropJob, StampJob
from models.lambda_event import LambdaEvent
from services.event_service import EventService


def test_event_service_can_parse_jobs():
    event_service = EventService()

    jobs_list = [
        {
            "command": "stamp",
            "output_file": "test.pdf",
            "image_file": "test_stamp.pdf",
        },
        {
            "command": "background",
            "output_file": "test.pdf",
            "image_file": "test_bg.pdf",
        },
    ]

    jobs = event_service.parse_jobs(jobs=jobs_list, input_file="test.pdf")

    expected_jobs: List[StampJob | BackgroundJob | CropJob] = []
    expected_jobs.append(
        StampJob(
            command="stamp",
            input_file="test.pdf",
            output_file="test.pdf",
            image_file="test_stamp.pdf",
        )
    )
    expected_jobs.append(
        BackgroundJob(
            command="background",
            input_file="test.pdf",
            output_file="test.pdf",
            image_file="test_bg.pdf",
        )
    )

    assert jobs == expected_jobs


def test_parsing_jobs_with_unknown_command_logs_a_warning():
    with capture_logs() as logs:
        event_service = EventService()

        jobs_list = [
            {
                "command": "unknown_command",
                "output_file": "test.pdf",
                "image_file": "test_stamp.pdf",
            },
        ]

        event_service.parse_jobs(jobs=jobs_list, input_file="test.pdf")

        assert {
            "event": "Invalid job received",
            "job": {
                "command": "unknown_command",
                "input_file": "test.pdf",
                "output_file": "test.pdf",
                "image_file": "test_stamp.pdf",
            },
            "log_level": "warning",
        } in logs


def test_parsing_jobs_without_command_logs_a_warning():
    with capture_logs() as logs:
        event_service = EventService()

        jobs_list = [
            {
                "output_file": "test.pdf",
                "image_file": "test_stamp.pdf",
            },
        ]

        event_service.parse_jobs(jobs=jobs_list, input_file="test.pdf")

        assert {
            "event": "Job is missing command, skipping job",
            "job": {
                "input_file": "test.pdf",
                "output_file": "test.pdf",
                "image_file": "test_stamp.pdf",
            },
            "log_level": "warning",
        } in logs


def test_running_event_service_parses_all_jobs():
    event_service = EventService()

    jobs_list = [
        {
            "command": "stamp",
            "image_file": "test_stamp.pdf",
        },
        {
            "command": "background",
            "image_file": "test_bg.pdf",
        },
    ]

    result = event_service.parse_jobs(jobs=jobs_list, input_file="test.pdf")

    expected_jobs: List[StampJob | BackgroundJob | CropJob] = []
    expected_jobs.append(
        StampJob(
            command="stamp",
            input_file="test.pdf",
            image_file="test_stamp.pdf",
        )
    )
    expected_jobs.append(
        BackgroundJob(
            command="background",
            input_file="test.pdf",
            image_file="test_bg.pdf",
        )
    )

    assert result == expected_jobs
