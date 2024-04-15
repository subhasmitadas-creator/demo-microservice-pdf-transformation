import os
import shutil
from unittest.mock import patch

import pytest

from errors.errors import ProcessorError
from models.jobs import PagesizeJob
from processors.pdfjam import PdfjamProcessor


def test_processor_raises_error_if_files_are_missing():
    processor = PdfjamProcessor()

    with pytest.raises(ProcessorError):
        processor.run(
            PagesizeJob(
                command="stamp",
                input_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/non_existing.pdf",
                nup_booklet=True,
                nup_columns=2,
                nup_rows=1,
                page_width=300,
                page_height=300,
                nup_frame=False,
                nup_delta_x=5,
                nup_delta_y=5,
            )
        )


def test_can_set_pagesize():
    shutil.copy2(
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/sample.pdf",
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/input.pdf",
    )
    processor = PdfjamProcessor()

    processor.run(
        PagesizeJob(
            command="stamp",
            input_file=os.path.dirname(os.path.abspath(__file__))
            + "/../assets/input.pdf",
            nup_booklet=True,
            nup_columns=2,
            nup_rows=1,
            page_width=300,
            page_height=300,
            nup_frame=False,
            nup_delta_x=5,
            nup_delta_y=5,
        )
    )

    assert os.path.getsize(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    ) == os.path.getsize(
        os.path.dirname(os.path.abspath(__file__))
        + "/../../tests/assets/sample_with_pagesize.pdf"
    )

    os.remove(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    )

    assert not os.path.exists(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    )
