"""Hugging Face Spaces Entrypoint (Gradio SDK Free Tier Compatible).

Hugging Face Gradio Spaces runs app.py automatically on port 7860 (CPU Basic - Free).
"""

import os
import uvicorn
from server import app

# Hugging Face expects 'app' in app.py
if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
