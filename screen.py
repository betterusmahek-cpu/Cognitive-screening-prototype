import json
import os
from http.server import BaseHTTPRequestHandler

from _lib.scoring import (
    validate_answers,
    compute_domain_scores,
    classify,
    ValidationError,
)
from _lib.llm import llm_extract_domains, LLMExtractionError

MAX_BODY_BYTES = 64 * 1024  # generous upper bound for a 30-answer payload


def _error_body(status, message):
    return status, json.dumps({"error": message}).encode("utf-8")


class handler(BaseHTTPRequestHandler):
    def _send(self, status, body_bytes):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_POST(self):
        try:
            length_header = self.headers.get("Content-Length", "0")
            try:
                length = int(length_header)
            except ValueError:
                status, body = _error_body(400, "invalid Content-Length header")
                self._send(status, body)
                return

            if length <= 0:
                status, body = _error_body(400, "request body is empty")
                self._send(status, body)
                return

            if length > MAX_BODY_BYTES:
                status, body = _error_body(413, "request body too large")
                self._send(status, body)
                return

            raw = self.rfile.read(length)

            try:
                payload = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                status, body = _error_body(400, "request body must be valid JSON")
                self._send(status, body)
                return

            if not isinstance(payload, dict) or "answers" not in payload:
                status, body = _error_body(400, 'request body must include an "answers" object')
                self._send(status, body)
                return

            try:
                answers = validate_answers(payload["answers"])
            except ValidationError as e:
                status, body = _error_body(400, str(e))
                self._send(status, body)
                return

            use_llm = bool(payload.get("use_llm", False))

            extraction_method = "deterministic"
            domains = None

            if use_llm:
                api_key = os.environ.get("OPENAI_API_KEY")
                if not api_key:
                    extraction_method = "deterministic_fallback_no_api_key"
                else:
                    try:
                        domains = llm_extract_domains(answers, api_key=api_key)
                        extraction_method = "llm"
                    except LLMExtractionError:
                        # Graceful fallback per spec section 6/13 -- never
                        # surface the underlying error to the participant.
                        domains = None
                        extraction_method = "deterministic_fallback_llm_error"

            if domains is None:
                domains = compute_domain_scores(answers)

            try:
                result = classify(domains)
            except ValidationError as e:
                status, body = _error_body(500, "internal scoring error")
                self._send(status, body)
                return

            result["meta"] = {"extraction_method": extraction_method}

            body = json.dumps(result).encode("utf-8")
            self._send(200, body)

        except Exception:
            # Never leak internal stack traces or key material to the client.
            status, body = _error_body(500, "an unexpected server error occurred")
            self._send(status, body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "POST, OPTIONS")
        self.end_headers()
