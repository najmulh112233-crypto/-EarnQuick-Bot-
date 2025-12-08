#!/bin/bash

# Initialize the database if it doesn't exist
python -c "from app import initialize_db; initialize_db()"

# Start the Gunicorn web server for the Flask app
gunicorn app:app -b 0.0.0.0:$PORT
