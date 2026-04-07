# Use the official lightweight Python image.
FROM python:3.11-slim

# Install system dependencies
# git is required by GitPython
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
RUN pip install --no-cache-dir -r api/requirements.txt uvicorn

# Set the PYTHONPATH so the application can resolve `roary.*`
ENV PYTHONPATH=/app/src

# Run the web service on container startup using uvicorn.
# Cloud Run injects the $PORT environment variable (default 8080).
CMD exec uvicorn roary.api.main:app --host 0.0.0.0 --port ${PORT:=8080}
