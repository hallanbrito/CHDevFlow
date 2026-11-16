# CHDevFlow F7 E3-B — runner stdlib-only, nao produtor de missoes nem publicador.
# Digest linux/amd64 fixado; nenhuma dependencia Python instalada via rede.
FROM --platform=linux/amd64 python:3.12-slim@sha256:05a994d2344eb364cc186910f4fc8786a38215f39f00d0acc25bff33a08f4177

ARG SOURCE_SHA
RUN test -n "$SOURCE_SHA"
LABEL org.opencontainers.image.source="https://github.com/hallanbrito/CHDevFlow" \
      org.opencontainers.image.revision="${SOURCE_SHA}" \
      org.opencontainers.image.title="CHDevFlow F7 E3-B Test Executor" \
      org.opencontainers.image.description="Executor isolado de testes sem agentes/segredos/publicacao"
COPY --chown=65534:65534 scripts/f7_executor_v1.py /opt/f7/runner.py
USER 65534:65534
WORKDIR /opt/f7
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-I", "-B", "/opt/f7/runner.py"]
CMD ["--self-check"]
