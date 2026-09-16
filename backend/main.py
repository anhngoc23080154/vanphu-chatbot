"""Entrypoint cho Vercel (zero-config: tìm biến `app` kiểu FastAPI)."""

from rag.api import create_app

app = create_app()
