FROM python:3.12-slim

WORKDIR /app

RUN groupadd -r generator && useradd -r -g generator generator

COPY data_generator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY data_generator/ ./data_generator/

RUN mkdir -p /app/data && chown -R generator:generator /app
USER generator

ENTRYPOINT ["python", "data_generator/generate_sales.py"]
CMD ["--rows", "1000", "--output", "data/sales.csv"]
