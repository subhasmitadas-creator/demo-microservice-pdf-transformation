from abc import ABC, abstractmethod

from models.jobs import Job


class PdfProcessor(ABC):
    @abstractmethod
    def run(self, job: Job):
        pass
