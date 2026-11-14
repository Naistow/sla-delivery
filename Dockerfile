FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY integration ./integration
COPY db ./db
COPY exchange ./exchange
COPY tests ./tests

CMD ["python", "-m", "app.main", "run-all"]
