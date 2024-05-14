import filecmp
import os
import shutil
from unittest.mock import patch

import pytest
from structlog.testing import capture_logs

from errors.errors import ProcessorError, FileDoesNotExistError
from models.jobs import BackgroundJob, StampJob
from processors.pdftk import PdftkProcessor


def test_can_add_stamp():
    shutil.copy2(
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/sample.pdf",
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/input.pdf",
    )
    processor = PdftkProcessor()

    with patch.object(
        processor,
        "download_watermark",
    ) as file_service_mock:
        file_service_mock.return_value = (
            os.path.dirname(os.path.abspath(__file__)) + "/../assets/watermark2.pdf"
        )

        processor.run(
            StampJob(
                command="stamp",
                input_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/input.pdf",
                image_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/watermark2.pdf",
            )
        )

    assert filecmp.cmp(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf",
        os.path.dirname(os.path.abspath(__file__))
        + "/../../tests/assets/sample_with_stamp.pdf",
    )

    os.remove(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    )

    assert not os.path.exists(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    )


def test_can_add_background():
    shutil.copy2(
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/sample.pdf",
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/input.pdf",
    )
    processor = PdftkProcessor()

    with patch.object(
        processor,
        "download_watermark",
    ) as file_service_mock:
        file_service_mock.return_value = (
            os.path.dirname(os.path.abspath(__file__)) + "/../assets/watermark2.pdf"
        )
        processor.run(
            BackgroundJob(
                command="background",
                input_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/input.pdf",
                image_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/watermark2.pdf",
            )
        )

    assert filecmp.cmp(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf",
        os.path.dirname(os.path.abspath(__file__))
        + "/../../tests/assets/sample_with_background.pdf",
    )

    os.remove(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    )

    assert not os.path.exists(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    )


def test_stamp_and_background_commands_dont_produce_same_result():
    shutil.copy2(
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/sample.pdf",
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/input.pdf",
    )
    assert os.path.exists(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    )
    shutil.copy2(
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/sample.pdf",
        os.path.dirname(os.path.abspath(__file__)) + "/../assets/input2.pdf",
    )
    assert os.path.exists(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input2.pdf"
    )
    processor = PdftkProcessor()

    with patch.object(
        processor,
        "download_watermark",
    ) as file_service_mock:
        file_service_mock.return_value = (
            os.path.dirname(os.path.abspath(__file__)) + "/../assets/watermark2.pdf"
        )

        processor.run(
            BackgroundJob(
                command="background",
                input_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/input2.pdf",
                image_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/watermark2.pdf",
            )
        )

        processor.run(
            StampJob(
                command="stamp",
                input_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/input.pdf",
                image_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/watermark2.pdf",
            )
        )

        assert os.path.getsize(
            os.path.dirname(os.path.abspath(__file__)) + "/../assets/input.pdf"
        ) != os.path.getsize(
            os.path.dirname(os.path.abspath(__file__)) + "/../assets/input2.pdf",
        )

    os.remove(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    )

    os.remove(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input2.pdf"
    )

    assert not os.path.exists(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input.pdf"
    )

    assert not os.path.exists(
        os.path.dirname(os.path.abspath(__file__)) + "/../../tests/assets/input2.pdf"
    )


def test_using_files_that_do_not_exist_raises_an_error():
    processor = PdftkProcessor()

    with capture_logs() as logs, pytest.raises(FileDoesNotExistError), pytest.raises(
        ProcessorError
    ), patch.object(
        processor,
        "download_watermark",
    ) as file_service_mock:
        file_service_mock.return_value = (
            os.path.dirname(os.path.abspath(__file__))
            + "/../assets/non_existing_file.pdf"
        )
        processor.run(
            BackgroundJob(
                command="background",
                output_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/tmp_background.pdf",
                input_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/non_existing_file.pdf",
                image_file=os.path.dirname(os.path.abspath(__file__))
                + "/../assets/non_existing_file.pdf",
            )
        )

    for log in logs:
        if log["event"] == "Failed while running pdftk":
            assert "Error: Unable to find file" in log["error"]
