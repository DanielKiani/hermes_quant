# Use Python 3.13 slim image as the base to maintain strict Dev/Prod parity
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for compiling ML libraries (XGBoost, ChromaDB, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code and assets
COPY src/ ./src/
COPY hermes_banner.png .

# Create the data directory so we can mount a persistent volume to it later
RUN mkdir -p data

# Expose the port Streamlit runs on
EXPOSE 8501

# Add a healthcheck to ensure the app is running
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Command to run the application
CMD ["streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0"]