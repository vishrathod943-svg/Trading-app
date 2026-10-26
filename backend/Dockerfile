FROM python:3.12-slim
WORKDIR /srv
COPY requirements.lock .
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then \
      PIP_CERT=/run/secrets/build_ca pip install --no-cache-dir -r requirements.lock; \
    else pip install --no-cache-dir -r requirements.lock; fi
RUN useradd --create-home screener && mkdir /data && chown screener /data
COPY --chown=screener:screener app app
USER screener
ENV FO_DATABASE=/data/screener.db FO_AUTO_DATABASE=/data/automation.db FO_MODE=demo
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
