FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./requirements.txt
COPY data_generator/requirements.txt ./data_generator-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r data_generator-requirements.txt

COPY . .

CMD ["python", "-m", "pytest", "tests/unit", "-v"]
