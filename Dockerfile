FROM python:3.9-bullseye as base
MAINTAINER ben <ben@sudo.is>

ENV DEBIAN_FRONTEND noninteractive
ENV TZ UTC
ENV TERM=xterm-256color

RUN apt-get update && \
        apt-get install -y libolm-dev libolm3 && \
        apt-get clean && \
        python3 -m pip install --upgrade pip

FROM base as builder

ARG BUILD_UID=1300
ENV PATH "$PATH:/home/builder/.local/bin"
WORKDIR /builder
RUN useradd -m -u ${BUILD_UID} -s /bin/bash builder && \
        chown builder:builder /builder
USER builder

RUN python3 -m pip install poetry

COPY pyproject.toml /builder
COPY poetry.lock /builder
COPY .flake8 /builder/
RUN poetry install --no-interaction --ansi --no-root


# copy the tests and code after installing dependencies
COPY tests /builder/tests/
COPY notflixbot /builder/notflixbot/
COPY README.md /builder/README.md
RUN poetry install --no-interaction --ansi

COPY config-sample.json /builder

RUN poetry run pytest || true
RUN poetry run flake8 || true
RUN poetry run isort . --check || true

RUN poetry build --no-interaction --ansi
RUN poetry export --without-hashes > /builder/requirements.txt

FROM base as final

COPY --from=builder /builder/requirements.txt /tmp
RUN python3 -m pip install -r /tmp/requirements.txt

COPY --from=builder /builder/dist/notflixbot-*.tar.gz /tmp
RUN python3 -m pip install /tmp/notflixbot-*.tar.gz && \
        rm -v /tmp/notflixbot-*.tar.gz /tmp/requirements.txt

COPY config.json /etc/notflixbot.json

# HEALTHCHECK --start-period=5s --interval=15s --timeout=1s \
#   CMD curl -f http://localhost:3333/api/ruok || exit 1
# EXPOSE 3333/tcp
CMD ["notflixbot", "-c", "/etc/notflixbot.json"]
