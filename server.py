"""
WP_Quản lý công việc — Server v3
"""
import os, json, threading, urllib.request, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT     = int(os.environ.get('PORT', 8765))
SUPA_URL = (os.environ.get('SUPABASE_URL') or '').rstrip('/')
SUPA_KEY = os.environ.get('SUPABASE_KEY') or ''
TABLE    = 'app_data'
ROW_ID   = 'taskflow_v3'
LOCK     = threading.Lock()

print("="*50)
print(f"  PORT     : {PORT}")
print(f"  SUPABASE : {'OK' if SUPA_URL and SUPA_KEY else 'MISSING'}")
print("="*50)

def _h():
    return {
        'apikey': SUPA_KEY,
        'Authorization': f'Bearer {SUPA_KEY}',
        'Content-Type': 'application/json',
    }

def ready():
    return bool(SUPA_URL and SUPA_KEY)

# Đọc dữ liệu từ Supabase
def supa_get():
    if not ready(): return None, 'no_config'
    url = f"{SUPA_URL}/rest/v1/{TABLE}?id=eq.{ROW_ID}&select=payload"
    try:
        req = urllib.request.Request(url, headers=_h())
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read().decode())
            if isinstance(rows, list) and rows:
                return rows[0].get('payload') or {}, 'ok'
            return {}, 'ok_empty'   # bảng rỗng = chưa có data lần đầu
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:300]
        print(f"[supa_get] {e.code}: {msg}")
        return None, f"http_{e.code}: {msg}"
    except Exception as e:
        print(f"[supa_get] {e}")
        return None, str(e)

# Ghi dữ liệu lên Supabase
def supa_upsert(data):
    if not ready(): return False, 'no_config'
    url = f"{SUPA_URL}/rest/v1/{TABLE}"
    body = json.dumps({'id': ROW_ID, 'payload': data}, ensure_ascii=False).encode()
    hdrs = {**_h(), 'Prefer': 'resolution=merge-duplicates,return=minimal'}
    try:
        req = urllib.request.Request(url, data=body, method='POST', headers=hdrs)
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"[supa_upsert] OK {len(body)//1024}KB")
            return True, 'ok'
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:300]
        print(f"[supa_upsert] {e.code}: {msg}")
        return False, f"http_{e.code}: {msg}"
    except Exception as e:
        print(f"[supa_upsert] {e}")
        return False, str(e)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if args and str(args[1]) not in ('200','204'):
            print(f"[HTTP] {fmt%args}")

    def cors(self):
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')

    def send_json(self, obj, st=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(st)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length', len(b))
        self.cors(); self.end_headers(); self.wfile.write(b)

    def do_OPTIONS(self):
        self.send_response(204); self.cors(); self.end_headers()

    def do_GET(self):
        p = self.path.split('?')[0]

        if p == '/api/data':
            with LOCK:
                data, _ = supa_get()
            self.send_json(data if data is not None else {})

        elif p == '/api/health':
            with LOCK:
                data, detail = supa_get()
            self.send_json({
                'status': 'ok',
                'mode': 'supabase' if ready() else 'no_db',
                'supabase_url_set': bool(SUPA_URL),
                'supabase_key_set': bool(SUPA_KEY),
                'supabase_ping': data is not None,
                'detail': detail,   # CHI TIẾT LỖI — để debug
            })

        elif p in ('/', '', '/index.html'):
            f = Path(__file__).parent / 'index.html'
            if f.exists():
                b = f.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Content-Length', len(b))
                self.end_headers(); self.wfile.write(b)
            else:
                self.send_response(404); self.end_headers()
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path.split('?')[0] == '/api/data':
            try:
                n = int(self.headers.get('Content-Length', 0))
                data = json.loads(self.rfile.read(n).decode())
                with LOCK:
                    ok, detail = supa_upsert(data)
                self.send_json({'ok': ok, 'detail': detail}, 200 if ok else 500)
            except Exception as e:
                print(f"[POST] {e}")
                self.send_json({'ok': False, 'error': str(e)}, 500)
        else:
            self.send_response(404); self.end_headers()

if __name__ == '__main__':
    if not ready():
        print("⚠️  SUPABASE_URL/KEY chưa cấu hình — dữ liệu sẽ không được lưu!")
    else:
        data, detail = supa_get()
        print(f"[Boot] Ping Supabase: {'OK' if data is not None else 'FAIL'} | {detail}")
    print(f"[Boot] Listening on port {PORT}")
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
