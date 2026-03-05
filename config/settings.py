"""
Module: config/settings.py
Responsibility: Loads environment variables into typed helpers so the rest
of the application never reads os.environ directly.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()  # reads .env if present


def get_database_path() -> str:
    return os.getenv("DATABASE_PATH", "./goodfoods.db")


def get_faiss_index_path() -> str:
    return os.getenv("FAISS_INDEX_PATH", "./embeddings/restaurant_index.faiss")


def get_groq_api_key() -> str:
    return os.getenv("GROQ_API_KEY", "")


def get_mcp_server_url() -> str:
    return os.getenv("MCP_SERVER_URL", "http://localhost:8000")


def get_mcp_api_key() -> str:
    return os.getenv("MCP_API_KEY", "")


def get_log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO")


def get_environment() -> str:
    return os.getenv("ENVIRONMENT", "development")
