FROM python:3.11-alpine

WORKDIR /app

RUN apk update && apk add --no-cache gcc musl-dev libffi-dev

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "web:app", "-w", "4", "-b", "0.0.0.0:8888"]
