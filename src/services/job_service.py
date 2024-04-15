from typing import List

from structlog import get_logger

from models.jobs import Job
from processors.processor_factory import ProcessorFactory


class JobService:
    errors: List[str] = []

    def __init__(self):
        self.logger = get_logger()

    def execute(self, job: Job):
        """
        Executes a specific job, e.g. StampJob via pdftk
        """
        processor_factory = ProcessorFactory()
        processor = processor_factory.new(job=job)

        processor.run(job)
