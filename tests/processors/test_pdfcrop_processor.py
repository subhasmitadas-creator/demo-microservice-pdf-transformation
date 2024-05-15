import os
import shutil
from unittest.mock import patch

import pytest

from errors.errors import ProcessorError
from models.jobs import CropJob
from processors.pdfcrop import PdfcropProcessor


def test_processor_raises_error_if_files_are_missing():
    processor = PdfcropProcessor()

    with pytest.raises(ProcessorError):
        processor.run(
            CropJob(
                command="crop",
                input_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/non_existing.pdf",
                margins=10,
                bounding_box_x=10,
                bounding_box_y=10,
            )
        )


def test_can_crop_pdf():
    shutil.copy2(
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/sample.pdf",
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/input.pdf",
    )
    processor = PdfcropProcessor()

    processor.run(
        CropJob(
            command="crop",
            input_file=os.path.dirname(os.path.abspath(__file__))
            + "/../assets/input.pdf",
            margins=10,
            bounding_box_x=500,
            bounding_box_y=600,
        )
    )

    assert os.path.getsize(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    ) == os.path.getsize(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/sample_with_crop.pdf"
    )

    os.remove(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    )

    assert not os.path.exists(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    )
