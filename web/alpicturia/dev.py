"""Convenience entrypoint for local development and managed preview."""

import argparse
import os
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--strictPort", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("PUBLIC_BASE_URL", f"http://{args.host}:{args.port}")
    uvicorn.run(
        "alpicturia.app:app",
        host=args.host,
        port=args.port,
        reload=False,
        access_log=False,
    )
