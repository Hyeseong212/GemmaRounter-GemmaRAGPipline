#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from sentence_transformers import SentenceTransformer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Small embedding helper for llama-rest-core vector retrieval.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18089)
    parser.add_argument("--model-name", default="BAAI/bge-m3")
    parser.add_argument("--device", default=None)
    return parser.parse_args()


def make_handler(model: SentenceTransformer):
    class Handler(BaseHTTPRequestHandler):
        def _json_response(self, status: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path != "/healthz":
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            self._json_response(
                HTTPStatus.OK,
                {"status": "ok", "model_name": model.model_card_data.base_model or "sentence-transformer"},
            )

        def do_POST(self) -> None:
            if self.path != "/embed":
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": "bad_json", "detail": str(exc)})
                return

            texts = payload.get("texts")
            if texts is None:
                text = payload.get("text")
                texts = [text] if isinstance(text, str) else None
            if not texts or not all(isinstance(item, str) and item.strip() for item in texts):
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": "bad_request", "detail": "text or texts is required"})
                return

            embeddings = model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            result = embeddings.tolist()
            if len(result) == 1:
                self._json_response(HTTPStatus.OK, {"embedding": result[0], "dim": len(result[0])})
            else:
                self._json_response(HTTPStatus.OK, {"embeddings": result, "dim": len(result[0])})

        def log_message(self, format: str, *args) -> None:
            return

    return Handler


def main() -> int:
    args = parse_args()
    model = SentenceTransformer(args.model_name, device=args.device)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(model))
    print(f"[rag-embed-helper] listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
