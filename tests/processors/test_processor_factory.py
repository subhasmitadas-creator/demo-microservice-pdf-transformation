from typing import List

import pytest

from errors.errors import CommandDoesNotExistError
from models.jobs import BackgroundJob, CropJob, Job, PagesizeJob, StampJob
from processors.pdfcrop import PdfcropProcessor
from processors.pdfjam import PdfjamProcessor
from processors.pdftk import PdftkProcessor
from processors.processor_factory import ProcessorFactory


def test_can_create_processors():
    jobs: List[Job] = []
    jobs.append(
        StampJob(
            command="stamp",
            input_file="test.pdf",
            image_file="test_stamp.pdf",
        )
    )
    jobs.append(
        BackgroundJob(
            command="background",
            input_file="test.pdf",
            image_file="test_bg.pdf",
        )
    )
    jobs.append(
        CropJob(
            command="crop",
            input_file="test.pdf",
            margins=5,
            bounding_box_x=5,
            bounding_box_y=5,
        )
    )
    jobs.append(
        PagesizeJob(
            command="pagesize",
            input_file="test.pdf",
            nup_booklet=False,
            nup_columns=1,
            nup_delta_x=1,
            nup_delta_y=1,
            nup_frame=True,
            nup_rows=1,
            page_height=100,
            page_width=100,
        )
    )

    processor_factory = ProcessorFactory()

    processor = processor_factory.new(jobs[0])
    assert isinstance(processor, PdftkProcessor)

    processor = processor_factory.new(jobs[1])
    assert isinstance(processor, PdftkProcessor)

    processor = processor_factory.new(jobs[2])
    assert isinstance(processor, PdfcropProcessor)

    processor = processor_factory.new(jobs[3])
    assert isinstance(processor, PdfjamProcessor)


def test_creating_processor_with_invalid_command_raises_an_error():
    job = StampJob(
        command="invalid_command",
        output_file="test.pdf",
        input_file="test.pdf",
        image_file="test_stamp.pdf",
    )

    processor_factory = ProcessorFactory()

    with pytest.raises(CommandDoesNotExistError):
        processor_factory.new(job)
