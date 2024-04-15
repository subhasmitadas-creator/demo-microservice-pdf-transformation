# Define custom function directory
ARG FUNCTION_DIR="/function"

FROM python:3.12 as build-image

# Include global arg in this stage of the build
ARG FUNCTION_DIR

# Copy function code
RUN mkdir -p ${FUNCTION_DIR}

COPY pyproject.toml ${FUNCTION_DIR}
COPY poetry.lock ${FUNCTION_DIR}
COPY src ${FUNCTION_DIR}/src
COPY tests ${FUNCTION_DIR}/tests

WORKDIR ${FUNCTION_DIR}

# Install the function's dependencies
RUN pip install \
    --target ${FUNCTION_DIR} \
        awslambdaric

# Use a slim version of the base Python image to reduce the final image size
FROM python:3.12-slim

# Include global arg in this stage of the build
ARG FUNCTION_DIR
# Set working directory to function root directory
WORKDIR ${FUNCTION_DIR}

# Copy in the built dependencies
COPY --from=build-image ${FUNCTION_DIR} ${FUNCTION_DIR}

RUN pip install poetry==1.7.1

RUN poetry config virtualenvs.in-project true
RUN poetry install

# install pdftk, pdfjam & pdfcrop
# The mount will cache the apt packages for faster build times
RUN --mount=target=/var/lib/apt/lists,type=cache,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install pdftk ghostscript -y && \
    apt-get install -y --no-install-recommends texlive-latex-recommended texlive-fonts-recommended && \
    apt-get install -y --no-install-recommends texlive-latex-extra texlive-extra-utils texlive-fonts-extra texlive-lang-all

ENV PYTHONPATH "${PYTHONPATH}:/function/src"

# Set runtime interface client as default command for the container runtime
ENTRYPOINT [ "poetry", "run", "python", "-m", "awslambdaric" ]
# Pass the name of the function handler as an argument to the runtime
CMD [ "src/main.handler" ]
