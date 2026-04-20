import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = int(os.environ.get('PORT', 8765))
DATA_FILE = Path(__file__).parent / 'data.json'
LOCK = threading.Lock()

def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding='utf-8'))
        except:
            pass
    return {}

def save_data(data):
    tmp = DATA_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(DATA_FILE)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # im logger

    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/data':
            with LOCK:
                data = load_data()
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', len(body))
            self.send_cors()
            self.end_headers()
            self.wfile.write(body)
        elif self.path in ('/', '/index.html', ''):
            html_path = Path(__file__).parent / 'index.html'
            if html_path.exists():
                body = html_path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', len(body))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/data':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode('utf-8'))
                with LOCK:
                    save_data(data)
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_cors()
                self.end_headers()
                self.wfile.write(b'{"ok":true}')
            except Exception as e:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'Server running on port {PORT}')
    server.serve_forever()
