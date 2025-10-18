# Use slim Python image
FROM python:3.11-slim

# Avoid writing pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create app user
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# Install system deps needed to build some wheels (kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Use non-root user
USER appuser

# Expose port
EXPOSE 8000

# Run the app with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
