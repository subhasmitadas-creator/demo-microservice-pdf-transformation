# Local Development

* Install python 3.12 (brew install python@3.12)
* Install poetry (pip3 install poetry)
* Using poetry, install dependencies (poetry install)
* Using poetry, enter the venv (poetry shell)

# Local testing (mocking lambda in AWS)

Run the image locally

```bash
make setup
make build
make run
```

Make a request locally
```bash
make request
```

After changes you need to restart the container

```bash
make restart
```

Viewing logs

```bash
make logs
```

Entering the container
```bash
make shell
```

Running tests
```bash
make test
```



# PDF Transformation
This is a microservice intended for transforming PDF files. During publication a user can publish as a PDF and use various settings, such as creating a booklet or adding a watermark. In order to offload Paligo and make PDF transformations more scalable, PDF transformation has been migrated to this microservice.

### How this microservice works
The intention is that microservices used in the Paligo infrastructure all work more or less similar. There exists a wrapper inside ccms that is called PdfTransformation that handles these API calls.
The microservice is hosted as a **Lambda** in AWS and uses **S3** to transfer files between CCMS and the microservice.

### How to build the image
Build the image with the following command;
```bash
make build
```
And then publish the image using the following command;
```bash
make publish
```

### Available PDF transformation jobs
This microservice allows you to use pdftk, pdfjam & pdfcrop to transform the PDF file. The currently available jobs are as follows:

#### PageSize
This job lets you set various page sizes for your PDF document.
Accepts the following parameters:
```json
{
    "nup_booklet": "bool",
    "nup_columns": "int",
    "nup_rows": "int",
    "page_width": "int",
    "page_height": "int",
    "nup_frame": "bool",
    "nup_delta_x": "int",
    "nup_delta_y": "int",
}
```

#### Crop
This job lets you crop a PDF.
Accepts the following parameters:
```json
{
    "margins": "int",
    "bounding_box_x": "int",
    "bounding_box_y": "int",
}
```

#### Background
This job adds a background (image background) to your PDF.
Accepts the following parameters:
```json
{
    "image_file": "string",
}
```

#### Stamp
This job adds a stamp (image on top) to your PDF.
Accepts the following parameters:
```json
{
    "image_file": "string",
}
```