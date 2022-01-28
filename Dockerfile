FROM python:3.9 as base

ENV DEBIAN_FRONTEND noninteractive
ENV TZ UTC
ENV TERM=xterm-256color

RUN apt-get update && apt-get install -y libolm-dev
RUN python3 -m pip install --upgrade pip

ARG UID=1216
RUN useradd -m -u ${UID} sudois \
        && mkdir /sudois \
        && chown sudois:sudois /sudois

WORKDIR /sudois

FROM base as builder
USER sudois

ENV PATH "$PATH:/home/sudois/.local/bin"

RUN python3 -m pip install --user poetry
COPY --chown=sudois:sudois pyproject.toml /sudois
COPY --chown=sudois:sudois poetry.lock /sudois
RUN poetry install --no-interaction --no-root --ansi

# copying the app code and leaving it there for
# the final and builder stages, rather than making
# a new stage to do that
COPY --chown=sudois:sudois . /sudois/
RUN poetry install --no-interaction --ansi

# should be in the jenkinsfile at some point
RUN poetry run pytest
RUN poetry run flake8

RUN poetry build --no-interaction --ansi

FROM builder as final
USER sudois
RUN poetry install --no-interaction --ansi

CMD ["notflixbot"]
