import os
import subprocess

from structlog import get_logger

from errors.errors import ProcessorError
from models.jobs import CropJob
from processors.processor import PdfProcessor


class PdfcropProcessor(PdfProcessor):
    def __init__(self) -> None:
        self.logger = get_logger()

    def run(self, job: CropJob):
        """
        Runs a pdfcrop job

        Raises
        ------
        ProcessorError if pdfcrop returns a non zero exit code
        """

        # fmt: off
        process = subprocess.run(
            [
                "pdfcrop",
                "--margins", f"{job.margins}",
                "--bbox", f"0 0 {job.bounding_box_x} {job.bounding_box_y}",
                job.input_file,
                f"{job.input_file}.result",
            ],
            capture_output=True,
            text=True,
            cwd=f"/tmp/",
        )
        # fmt: on

        if process.returncode != 0:
            self.logger.exception(
                "Failed while running pdfcrop",
                output=process.stdout,
                error=process.stderr,
            )
            raise ProcessorError("Failed while running pdfcrop")

        # Replace input file with the newly processed file
        os.replace(f"{job.input_file}.result", job.input_file)
