import os
import subprocess

from structlog import get_logger

from errors.errors import ProcessorError
from models.jobs import PagesizeJob
from processors.processor import PdfProcessor


class PdfjamProcessor(PdfProcessor):
    def __init__(self) -> None:
        self.logger = get_logger()

    def run(self, job: PagesizeJob):
        """
        Runs a pdfjam job

        Raises
        ------
        ProcessorError if pdfjam returns a non zero exit code
        """

        paper_size_x = (
            job.nup_columns * job.page_width + (job.nup_columns - 1) * job.nup_delta_x
        )
        paper_size_y = (
            job.nup_rows * job.page_height + (job.nup_rows - 1) * job.nup_delta_y
        )

        frame_value = "true" if job.nup_frame else "false"
        booklet_value = "true" if job.nup_booklet else ""
        booklet = "--booklet" if job.nup_booklet else ""

        # fmt: off
        process = subprocess.run(
            [
                "pdfjam",
                booklet, booklet_value,
                '--nup', f"{job.nup_columns}x{job.nup_rows}",
                "--papersize", f"{{{paper_size_x}pt,{paper_size_y}pt}}",
                "--templatesize", f"{{{job.page_width}pt}}{{{job.page_height}pt}}",
                "--frame", frame_value,
                "--delta", f"{job.nup_delta_x}pt {job.nup_delta_y}pt",
                "--outfile", f"{job.input_file}.result",
                job.input_file
            ],
            capture_output=True,
            text=True,
        )
        # fmt: on

        if process.returncode != 0:
            self.logger.exception(
                "Failed while running pdfjam",
                output=process.stdout,
                error=process.stderr,
            )
            raise ProcessorError("Failed while running pdfjam")

        # Replace input file with the newly processed file
        os.replace(f"{job.input_file}.result", job.input_file)
