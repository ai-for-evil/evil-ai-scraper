#!/usr/bin/env python3
"""Entry point for the Evil AI Scraper v2 web application."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8001, reload=True)
