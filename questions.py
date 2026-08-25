import json
from http.server import BaseHTTPRequestHandler

from _lib.questions_data import QUESTIONS, SECTIONS, SCALES


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        payload = {
            "questions": QUESTIONS,
            "sections": SECTIONS,
            "scales": SCALES,
        }
        body = json.dumps(payload).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, OPTIONS")
        self.end_headers()
