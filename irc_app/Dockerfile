FROM python:3.12-slim

WORKDIR /app

# Copy requirements and install
COPY irc_app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything into /app
COPY . .

# Set PYTHONPATH so 'import app' works from anywhere
ENV PYTHONPATH=/app

# IMPORTANT: Run the main app, not the service file
# This is what starts the Dash server and keeps the container alive
CMD ["python", "-u", "-m", "app.main"]