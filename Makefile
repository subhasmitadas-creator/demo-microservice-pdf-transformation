IMAGE_NAME = "microservice-pdf"
S3_BUCKET = "microservice-pdf"
version = 1.0.1

DOCKER_RUN_CMD = \
	docker run --platform linux/arm64 -d \
	--name microservice.pdftransformation \
	-p 9000:8080 \
	-v ${PWD}/src:/function/src:cached \
	-v ${PWD}/tests:/function/tests:cached \
	--network paligo_backend \
	--env-file .env \
    --entrypoint /aws-lambda/aws-lambda-rie \
    microservice-pdf:latest \
        poetry run python -m awslambdaric src/main.handler

DOCKER_BUILD_CMD = \
	docker build --platform linux/arm64 -t ${IMAGE_NAME}:latest .

CONTAINER_ID := $(shell docker ps -a --filter ancestor=${IMAGE_NAME}:latest --format="{{.ID}}")

all: run build stop shell test logs restart request test-verbose
.PHONY: all

run: 
ifeq ("$(wildcard .env)","")
	$(error .env file is missing, please copy the example env file!)
else
	$(DOCKER_RUN_CMD)
endif

build:
	$(DOCKER_BUILD_CMD)

test:
	docker exec -it $(CONTAINER_ID) poetry run pytest tests --disable-warnings

test-verbose:
	docker exec -it $(CONTAINER_ID) poetry run pytest ./tests -v --durations=0

request-stamp:
	curl "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{"isBase64Encoded":false,"body":{"input":"sample.pdf", "jobs": [{"command": "stamp", "image_file": "watermark2.pdf"}]}}'

request-pagesize:
	curl "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{"isBase64Encoded":false,"body":{"input":"sample.pdf","jobs":[{"command":"pagesize","nup_booklet":true,"nup_columns":2,"nup_rows":1,"page_width":300,"page_height":300,"nup_frame":false,"nup_delta_x":5,"nup_delta_y":5}]}}'

request-crop:
	curl "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{"isBase64Encoded":false,"body":{"input":"sample.pdf","jobs":[{"command":"crop","margins":5,"bounding_box_x":5,"bounding_box_y":5}]}}'

request-playground: 
	curl http://HenricTestPdfLb-1320450767.eu-north-1.elb.amazonaws.com -H "Accept: application/json"-d '{"test":"test"}'

download:
	aws --profile localstack s3 cp s3://$(S3_BUCKET)/completed_file.pdf completed_file.pdf

setup:
ifeq ("$(wildcard .env)","")
	cp .env.example .env
endif
	aws --profile localstack s3api create-bucket --bucket $(S3_BUCKET) --region us-east-1
	aws --profile localstack s3api put-object --bucket $(S3_BUCKET) --key sample.pdf --body tests/assets/sample.pdf
	aws --profile localstack s3api put-object --bucket $(S3_BUCKET) --key watermark2.pdf --body tests/assets/watermark2.pdf

stop:
	docker stop $(CONTAINER_ID)
	docker rm $(CONTAINER_ID)

shell:
	docker exec -it $(CONTAINER_ID) bash

publish:
	docker tag $(IMAGE_NAME) 397662812780.dkr.ecr.eu-west-1.amazonaws.com/microservice-pdftransformation:latest
	docker tag $(IMAGE_NAME) 397662812780.dkr.ecr.eu-west-1.amazonaws.com/microservice-pdftransformation:$(version)
	docker push 397662812780.dkr.ecr.eu-west-1.amazonaws.com/microservice-pdftransformation:latest
	docker push 397662812780.dkr.ecr.eu-west-1.amazonaws.com/microservice-pdftransformation:$(version)

logs:
	docker logs $(CONTAINER_ID)

restart: stop run