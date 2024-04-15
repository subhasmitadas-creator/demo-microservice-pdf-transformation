import os
import pathlib
import tempfile

import boto3
from botocore.exceptions import ClientError
from structlog import get_logger


class FileService:
    client: boto3.session.Session.client
    inbound_bucket: str
    outbound_bucket: str

    def __init__(self) -> None:
        self.client = boto3.client("s3")
        self.inbound_bucket = os.getenv("S3_BUCKET_INBOUND")
        self.outbound_bucket = os.getenv("S3_BUCKET_OUTBOUND")
        self.logger = get_logger()

    def download_file_from_s3(self, file_name: str) -> bool | str:
        """Downloads a file from S3 and returns the locally created file name"""
        if not os.path.exists(f"/tmp"):
            os.mkdir(f"/tmp")

        tmp_file_name = self.generate_filename() + pathlib.Path(file_name).suffix
        try:
            self.client.download_file(self.inbound_bucket, file_name, f"/tmp/{tmp_file_name}")
        except ClientError as e:
            self.logger.exception(
                "Error occured during file download from S3 bucket",
                bucket=self.inbound_bucket,
                file_name=file_name,
                exception=e,
            )
            return False

        return tmp_file_name

    def upload_file_to_s3(self, upload_file_name: str, output_file: str) -> bool:
        """Uploads a file to S3"""
        try:
            self.client.upload_file(
                f"/tmp/{upload_file_name}", self.outbound_bucket, output_file
            )
        except ClientError as e:
            self.logger.exception(
                "Error occured during file upload to S3 bucket",
                bucket=self.outbound_bucket,
                upload_file_name=upload_file_name,
                output_file=output_file,
                exception=e,
            )
            return False

        return True

    def generate_filename(self) -> str:
        """Generates a temporary file name"""
        return next(tempfile._get_candidate_names())
