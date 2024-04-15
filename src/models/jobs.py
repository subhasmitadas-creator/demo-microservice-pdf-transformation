from pydantic import BaseModel


class Job(BaseModel):
    command: str
    input_file: str


class StampJob(Job):
    image_file: str


class BackgroundJob(Job):
    image_file: str


class CropJob(Job):
    margins: int
    bounding_box_x: int
    bounding_box_y: int


class PagesizeJob(Job):
    nup_booklet: bool
    nup_columns: int
    nup_rows: int
    page_width: int
    page_height: int
    nup_frame: bool
    nup_delta_x: int
    nup_delta_y: int
