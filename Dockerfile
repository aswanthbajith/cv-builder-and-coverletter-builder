FROM python:3.12-slim

# Install system dependencies for LaTeX compilation
RUN apt-get update && apt-get install -y \
    texlive-xetex \
    texlive-fonts-recommended \
    texlive-latex-extra \
    fonts-lmodern \
    pandoc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p input profile templates generated output

# Set environment variables
ENV PYTHONPATH=/app/src
ENV CONFIG_PATH=/app/config.yaml

# Run the application
CMD ["python", "src/main.py"]
