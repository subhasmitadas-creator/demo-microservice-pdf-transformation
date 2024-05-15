from constants import BACKGROUND_COMMAND, STAMP_COMMAND
from errors.errors import CommandDoesNotExistError
from models.jobs import Job
from processors.pdfcrop import PdfcropProcessor
from processors.pdfjam import PdfjamProcessor
from processors.pdftk import PdftkProcessor
from processors.processor import PdfProcessor


class ProcessorFactory:
    def new(self, job: Job) -> PdfProcessor:
        """
        Creates a new PdfProcessor based on job command

        Raises
        ------
        CommandDoesNotExistError if command does not exist
        """
        match job.command:
            case "stamp" | "background":
                processor = PdftkProcessor()
            case "crop":
                processor = PdfcropProcessor()
            case "pagesize":
                processor = PdfjamProcessor()
            case _:
                raise CommandDoesNotExistError

        return processor
