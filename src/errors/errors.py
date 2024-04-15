from errors.microservice_error import MicroserviceError


class CommandDoesNotExistError(MicroserviceError):
    pass


class ProcessorError(MicroserviceError):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class InputFileDoesNotExistError(MicroserviceError):
    pass


class FileDoesNotExistError(MicroserviceError):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class OutputFileDoesNotExistError(MicroserviceError):
    pass
