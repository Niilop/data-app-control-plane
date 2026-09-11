# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt /app/

# Install dependencies (adjust if you have requirements.txt)
RUN pip install --no-cache-dir -r requirements.txt

# Copy only backend folder contents into /app
COPY ./backend /app

# Run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]