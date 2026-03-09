FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/
COPY manifests/ ./manifests/
COPY benchmarks/ ./benchmarks/
COPY examples/ ./examples/
COPY pyproject.toml .

# Install the package in editable mode
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src

EXPOSE 8080

CMD ["python", "examples/basic/02_hypervisor_demo.py"]
