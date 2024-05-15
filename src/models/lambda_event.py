from pydantic import BaseModel


class LambdaEvent(BaseModel):
    jobs: list
    input: str
