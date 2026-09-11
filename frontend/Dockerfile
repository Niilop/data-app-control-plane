# frontend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy only frontend folder contents into /app
COPY ./frontend /app

COPY frontend/requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]