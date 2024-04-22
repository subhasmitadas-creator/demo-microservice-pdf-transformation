import uuid
from typing import List

from pydantic_core import ValidationError
from structlog import get_logger

import constants
from errors.errors import CommandDoesNotExistError, ProcessorError
from models.jobs import BackgroundJob, CropJob, Job, PagesizeJob, StampJob
from models.lambda_event import LambdaEvent
from models.response import ResponseObject
from services.file_service import FileService
from services.job_service import JobService


class EventService:
    jobs: List[Job] = []
    logger = get_logger()

    def process_jobs(self, response: ResponseObject) -> ResponseObject:
        """Processes the jobs"""
        job_service = JobService()

        for job in self.jobs:
            try:
                job_service.execute(job)
            except CommandDoesNotExistError as e:
                self.logger.exception("Command does not exist", exception=e)
                response.add_error(f"Command '{job.command}' does not exist")
                return response
            except ProcessorError as e:
                self.logger.exception(
                    "Exception occured while running job", exception=e
                )
                response.add_error(
                    "pdf transformation returned a non empty response, check logs for more information"
                )
                return response

        return response

    def run(self, event: LambdaEvent) -> ResponseObject:
        """
        Runs the event
        """
        response = ResponseObject()
        file_service = FileService()

        self.logger.info("Downloading file from S3", file_name=event.input)
        input_file = file_service.download_file_from_s3(event.input)

        if not input_file:
            self.logger.error("Error occured when downloading file, aborting.")
            response.add_error(
                f"Error occured during file download, does the input file exist ({event.input})?"
            )
            return response

        self.logger.info("Validating jobs", jobs=event.jobs)
        self.jobs = self.parse_jobs(jobs=event.jobs, input_file=f"/tmp/{input_file}")

        if len(self.jobs) < len(event.jobs):
            response.add_error(
                "Failed parsing some jobs, check logs for more information"
            )
            return response

        self.process_jobs(response)

        output_file = uuid.uuid4().hex + ".pdf"
        self.logger.info(
            "Uploading file to S3", file_name=input_file, output_file=output_file
        )
        if not file_service.upload_file_to_s3(input_file, output_file):
            self.logger.error("Failed uploading file to S3 bucket")
            response.add_error("Error occured during file upload")
            return response

        if response.status_code == 200:
            response.message = f"Job(s) completed and {output_file} uploaded to S3."
            response.output_file = output_file

        return response

    def parse_jobs(self, jobs: list, input_file: str) -> List[Job]:
        """
        Parses a list of jobs into a list of models, will log a warning
        if command is not found
        """
        parsed_jobs: List[Job] = []

        for job in jobs:
            job["input_file"] = input_file
            if not "command" in job:
                self.logger.warning("Job is missing command, skipping job", job=job)
                continue

            try:
                match job["command"]:
                    case constants.STAMP_COMMAND:
                        parsed_jobs.append(StampJob.model_validate(job))
                    case constants.BACKGROUND_COMMAND:
                        parsed_jobs.append(BackgroundJob.model_validate(job))
                    case constants.CROP_COMMAND:
                        parsed_jobs.append(CropJob.model_validate(job))
                    case constants.PAGESIZE_COMMAND:
                        parsed_jobs.append(PagesizeJob.model_validate(job))
                    case _:
                        self.logger.warning("Invalid job received", job=job)
            except ValidationError as e:
                self.logger.exception(
                    "Failed while validating job", job=job, exception=e
                )

        self.logger.info("Jobs validated", jobs=parsed_jobs)
        return parsed_jobs
