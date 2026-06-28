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

# Copy project metadata first for layer caching of the dependency install.
COPY pyproject.toml README.md ./
# Copy only the package directory — the legacy src/ engines are excluded
# from the wheel build (see pyproject.toml [tool.hatch.build.targets.wheel]).
COPY src/job_automation ./src/job_automation

# Install the package in editable mode so the `job-automation` console
# script and the `job_automation` import path are available everywhere.
RUN pip install --no-cache-dir -e .

# Copy the remaining sources (legacy engines, configs, profile, etc.) used
# by the migration shim.
COPY src/ ./src/
COPY config.yaml profile/ templates/ input/ ./

# Create necessary directories
RUN mkdir -p input profile templates generated output

# Set environment variables. JOB_AUTO_LOGGING__FORMAT=json switches the
# logger to JSON output for production log shipping.
ENV JOB_AUTO_LOGGING__FORMAT=json

# Run via the installed console script. M3 will swap this for the Celery
# worker entry point.
CMD ["job-automation"]
