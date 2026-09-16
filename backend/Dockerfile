FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

COPY backend/requirements.txt /code/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/backend/requirements.txt

COPY backend /code/backend

EXPOSE 8000

CMD ["fastapi", "run", "backend/app/main.py", "--port", "8000"]
