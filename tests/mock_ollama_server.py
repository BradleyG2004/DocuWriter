from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import time


class OllamaHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[mock-ollama] {format % args}", flush=True)

    def do_GET(self):
        if self.path != "/api/tags":
            self.send_error(404)
            return
        body = json.dumps({"models": [{"name": "llama3.1:latest"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/generate":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            prompt = payload.get("prompt")
            model = payload.get("model")
            if not isinstance(prompt, str) or not isinstance(model, str):
                raise ValueError("prompt and model must be strings")
            if payload.get("format") != "json":
                raise ValueError("format must be json")
            if "<here>" in prompt or "</here>" in prompt:
                raise ValueError("malformed here tags in prompt")
            indices = [int(value) for value in re.findall(r"\[(\d+)\]", prompt)]
            if "Context:" not in prompt or "Placeholders:" not in prompt or not indices:
                raise ValueError("prompt lacks BM25 context or placeholder indices")
            time.sleep(0.15)
            replacements = [
                {
                    "index": index,
                    "replacement": "Contenu technique généré et validé par IA pour la section correspondante.",
                }
                for index in sorted(set(indices))
            ]
            body = json.dumps({
                "model": "llama3.1",
                "done": True,
                "response": json.dumps({"replacements": replacements}),
            }).encode()
            status = 200
        except (json.JSONDecodeError, ValueError) as exc:
            body = json.dumps({"error": str(exc)}).encode()
            status = 400
            print(f"[mock-ollama] HTTP 400: {exc}", flush=True)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 11435), OllamaHandler).serve_forever()
