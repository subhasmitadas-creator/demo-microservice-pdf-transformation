import json
from typing import List


class ResponseObject:
    errors: List[str]
    message: str
    output_file: str
    status_code: int

    def __init__(self):
        self.errors = []
        self.status_code = 200
        self.message = ""
        self.output_file = ""

    def format_object(self):
        """Formats the object for output"""
        return {
            "statusCode": self.status_code,
            "body": json.dumps({"message": self.message, "errors": self.errors, "output_file": self.output_file}),
        }
    
    def add_error(self, error_msg: str, status_code: int = 500):
        self.errors.append(error_msg)
        self.status_code = status_code
