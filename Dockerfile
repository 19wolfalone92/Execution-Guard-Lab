# Deployment candidate; not built or published during local qualification.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements-runtime.txt production_preflight.py ./
RUN python -m pip install --no-cache-dir --only-binary=:all: -r requirements-runtime.txt && python -m pip check && python production_preflight.py
COPY lab.py extensions.py secure_http.py ./
USER 10001:10001
EXPOSE 8443
CMD ["python","secure_http.py"]
