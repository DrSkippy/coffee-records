"""Gunicorn settings sourced from config.yaml's ``server`` block."""

from coffee_records.config import load_config

_server = load_config().server

bind = f"{_server.host}:{_server.port}"
workers = _server.workers
