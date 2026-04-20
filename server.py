"""
WP_Quản lý công việc — Server (Supabase PostgreSQL)
Dữ liệu lưu trên Supabase, dùng chung cho mọi máy.
"""
import os, json, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import urllib.request, urllib.error

PORT = int(os.environ.get('PORT', 8765))

# === SUPABASE CONFIG (điền vào Environment Variables trên Render) ===
SUPA_URL  = os.environ.get('SUPABASE_URL', '')   # ví dụ: https://abcxyz.supabase.co
SUPA_KEY  = os.environ.get('SUPABASE_KEY', '')   # anon/public key
TABLE     = 'app_data'
ROW_ID    = 'taskflow_v3'

# === FALLBACK: lưu file nếu chưa cấu hình Supabase ===
DATA_FILE = Path(__file__).parent / 'data.json'
LOCK      = threading.Lock()

# In-memory cache để giảm số lần gọi DB
_cache = None
_cache_dirty = False

# ─── Supabase helpers ─────────────────────────────────────────────────────────

def supa_get():
    """Đọc dữ liệu từ Supabase."""
    if not SUPA_URL or not SUPA_KEY:
        return None
    url = f"{SUPA_URL}/rest/v1/{TABLE}?id=eq.{ROW_ID}&select=payload"
    req = urllib.request.Request(url, headers={
        'apikey': SUPA_KEY,
        'Authorization': f'Bearer {SUPA_KEY}',
        'Content-Type': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            rows = json.loads(r.read())
            if rows:
                return rows[0].get('payload', {})
    except Exception as e:
        print(f'[supa_get error] {e}')
    return None

def supa_upsert(data):
    """Ghi dữ liệu vào Supabase (upsert = insert hoặc update)."""
    if not SUPA_URL or not SUPA_KEY:
        return False
    url = f"{SUPA_URL}/rest/v1/{TABLE}"
    body = json.dumps({'id': ROW_ID, 'payload': data}, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=body, method='POST', headers={
        'apikey': SUPA_KEY,
        'Authorization': f'Bearer {SUPA_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'resolution=merge-duplicates',
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status in (200, 201)
    except Exception as e:
        print(f'[supa_upsert error] {e}')
    return False

# ─── Load / Save với fallback ─────────────────────────────────────────────────

def load_data():
    global _cache
    if _cache is not None:
        return _cache
    # Thử Supabase trước
    data = supa_get()
    if data is not None:
        print('[DB] Loaded from Supabase')
        _cache = data
        return data
    # Fallback: file local
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding='utf-8'))
            print('[DB] Loaded from local file (fallback)')
            _cache = data
            return data
        except:
            pass
    print('[DB] No existing data, starting fresh')
    _cache = {}
    return _cache

def save_data(data):
    global _cache, _cache_dirty
    _cache = data
    # Ghi Supabase
    ok = supa_upsert(data)
    if ok:
        print('[DB] Saved to Supabase')
    else:
        # Fallback: ghi file
        try:
            tmp = DATA_FILE.with_suffix('.tmp')
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            tmp.replace(DATA_FILE)
            print('[DB] Saved to local file (fallback)')
        except Exception as e:
            print(f'[DB] Save failed: {e}')

# ─── HTTP Handler ─────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # tắt log mặc định

    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/api/data':
            with LOCK:
                data = load_data()
            self.send_json(data)

        elif self.path == '/api/health':
            mode = 'supabase' if (SUPA_URL and SUPA_KEY) else 'local_file'
            self.send_json({'status': 'ok', 'mode': mode})

        elif self.path.split('?')[0] in ('/', '/index.html'):
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
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                data = json.loads(body.decode('utf-8'))
                with LOCK:
                    save_data(data)
                self.send_json({'ok': True})
            except Exception as e:
                print(f'[POST /api/data error] {e}')
                self.send_json({'ok': False, 'error': str(e)}, 500)
        else:
            self.send_response(404)
            self.end_headers()

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    mode = 'Supabase' if (SUPA_URL and SUPA_KEY) else 'Local file (fallback)'
    print(f'=== WP_Quản lý công việc ===')
    print(f'Port  : {PORT}')
    print(f'Mode  : {mode}')
    if not SUPA_URL:
        print('WARN  : SUPABASE_URL chưa cấu hình — dùng file local, dữ liệu sẽ mất khi Render restart!')
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    server.serve_forever()
