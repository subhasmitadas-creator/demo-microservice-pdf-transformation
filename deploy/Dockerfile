# Dual-mode image: one build, one ECR tag, two runtimes — no application code
# changes required.
#
#   Lambda -> default ENTRYPOINT (awslambdaric), talks to the real Lambda
#             Runtime API.
#   ECS    -> task definition prefixes the entrypoint with aws-lambda-rie, the
#             AWS Runtime Interface Emulator, which serves the same handler over
#             HTTP on port 8080.
#
# Kept separate from the repo-root Dockerfile so the existing Lambda build and
# the test image stay exactly as they are.

ARG FUNCTION_DIR="/function"

FROM python:3.12 AS build-image

ARG FUNCTION_DIR

RUN mkdir -p ${FUNCTION_DIR}

# Runtime Interface Emulator — this is what lets the ECS task serve HTTP
# without a web framework. Same download the repo-root Dockerfile uses.
RUN mkdir -p /aws-lambda && curl -Lo /aws-lambda/aws-lambda-rie \
    https://github.com/aws/aws-lambda-runtime-interface-emulator/releases/latest/download/aws-lambda-rie-arm64 \
    && chmod +x /aws-lambda/aws-lambda-rie

COPY pyproject.toml ${FUNCTION_DIR}
COPY poetry.lock ${FUNCTION_DIR}
COPY src ${FUNCTION_DIR}/src

WORKDIR ${FUNCTION_DIR}

# Lambda runtime interface client, installed flat into the function directory
# the way the AWS base images expect.
RUN pip install --target ${FUNCTION_DIR} awslambdaric

FROM python:3.12-slim

ARG FUNCTION_DIR
WORKDIR ${FUNCTION_DIR}

COPY --from=build-image ${FUNCTION_DIR} ${FUNCTION_DIR}
COPY --from=build-image /aws-lambda /aws-lambda

RUN pip install poetry==1.7.1

RUN poetry config virtualenvs.in-project true
RUN poetry install --no-root

# pdftk, pdfjam & pdfcrop — the actual PDF toolchain.
RUN --mount=target=/var/lib/apt/lists,type=cache,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install pdftk ghostscript -y && \
    apt-get install -y --no-install-recommends texlive-latex-recommended texlive-fonts-recommended && \
    apt-get install -y --no-install-recommends texlive-latex-extra texlive-extra-utils texlive-fonts-extra texlive-lang-all && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONPATH="${PYTHONPATH}:/function/src"

# Default: Lambda. ECS prepends aws-lambda-rie via the task definition.
ENTRYPOINT [ "poetry", "run", "python", "-m", "awslambdaric" ]
CMD [ "src/main.handler" ]
