import os
import subprocess

from structlog import get_logger

from errors.errors import ProcessorError, FileDoesNotExistError
from models.jobs import Job
from processors.processor import PdfProcessor
from services.file_service import FileService


class PdftkProcessor(PdfProcessor):
    def __init__(self) -> None:
        self.logger = get_logger()

    def download_watermark(self, s3_filename: str) -> str:
        """Downloads the watermark file"""
        file_service = FileService()

        watermark_file_name = file_service.download_file_from_s3(s3_filename)
        watermark_path = f"/tmp/{watermark_file_name}"

        return watermark_path

    def run(self, job: Job):
        """
        Runs a pdftk job (stamp/background)

        Raises
        ------
        ProcessorError if pdftk returns a non zero exit code
        """

        watermark_path = self.download_watermark(job.image_file)

        if not os.path.exists(watermark_path):
            raise FileDoesNotExistError(f"Image file does not exist ({job.image_file})")

        shell_command = f"pdftk {job.input_file} {job.command} {watermark_path} output {job.input_file}.result"
        self.logger.info("Executing pdftk shell command", command=shell_command)

        process = subprocess.run(
            shell_command.split(" "), capture_output=True, text=True
        )

        if process.returncode != 0:
            self.logger.exception(
                "Failed while running pdftk",
                output=process.stdout,
                error=process.stderr,
            )
            raise ProcessorError("Failed while running pdftk")

        # Replace input file with the newly processed file
        os.replace(f"{job.input_file}.result", job.input_file)
