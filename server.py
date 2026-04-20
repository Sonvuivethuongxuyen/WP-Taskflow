"""
WP_Quản lý công việc — Server
Lưu dữ liệu trên Supabase (dùng chung cho mọi máy, mọi lúc).
"""
import os, json, threading, urllib.request, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT      = int(os.environ.get('PORT', 8765))
SUPA_URL  = (os.environ.get('SUPABASE_URL') or '').rstrip('/')
SUPA_KEY  = os.environ.get('SUPABASE_KEY') or ''
TABLE     = 'app_data'
ROW_ID    = 'taskflow_v3'
LOCK      = threading.Lock()

print("=" * 50)
print("  WP_Quản lý công việc — Server khởi động")
print(f"  PORT     : {PORT}")
print(f"  SUPABASE : {'✓ CÓ' if SUPA_URL and SUPA_KEY else '✗ CHƯA CẤU HÌNH'}")
print("=" * 50)

def _h():
    return {'apikey': SUPA_KEY, 'Authorization': f'Bearer {SUPA_KEY}', 'Content-Type': 'application/json'}

def ready():
    return bool(SUPA_URL and SUPA_KEY)

def supa_get():
    if not ready(): return None
    url = f"{SUPA_URL}/rest/v1/{TABLE}?id=eq.{ROW_ID}&select=payload"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_h()), timeout=15) as r:
            rows = json.loads(r.read().decode())
            if isinstance(rows, list) and rows:
                return rows[0].get('payload') or {}
            return {}
    except urllib.error.HTTPError as e:
        print(f"[supa_get] HTTPError {e.code}: {e.read().decode()[:200]}")
    except Exception as e:
        print(f"[supa_get] Error: {e}")
    return None

def supa_upsert(data):
    if not ready(): return False
    url = f"{SUPA_URL}/rest/v1/{TABLE}"
    body = json.dumps({'id': ROW_ID, 'payload': data}, ensure_ascii=False).encode()
    hdrs = {**_h(), 'Prefer': 'resolution=merge-duplicates,return=minimal'}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method='POST', headers=hdrs), timeout=15) as r:
            ok = r.status in (200, 201)
            if ok: print(f"[supa_upsert] Saved {len(body)//1024}KB")
            return ok
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"[supa_upsert] HTTPError {e.code}: {err[:300]}")
    except Exception as e:
        print(f"[supa_upsert] Error: {e}")
    return False

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if args and str(args[1]) not in ('200','204'): print(f"[HTTP] {fmt%args}")

    def cors(self):
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')

    def json(self, obj, st=200):
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
            with LOCK: data = supa_get()
            self.json(data if data is not None else {})
        elif p == '/api/health':
            with LOCK: ping = supa_get()
            self.json({'status':'ok','mode':'supabase' if ready() else 'no_db',
                       'supabase_url_set':bool(SUPA_URL),'supabase_key_set':bool(SUPA_KEY),
                       'supabase_ping': ping is not None})
        elif p in ('/','','/index.html'):
            f = Path(__file__).parent/'index.html'
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
                n = int(self.headers.get('Content-Length',0))
                data = json.loads(self.rfile.read(n).decode())
                with LOCK: ok = supa_upsert(data)
                self.json({'ok': ok}, 200 if ok else 500)
            except Exception as e:
                print(f"[POST] Error: {e}"); self.json({'ok':False,'error':str(e)}, 500)
        else:
            self.send_response(404); self.end_headers()

if __name__ == '__main__':
    if not ready():
        print("\n⚠️  SUPABASE_URL và SUPABASE_KEY chưa được cấu hình!")
        print("   Dữ liệu sẽ KHÔNG được lưu. Thêm vào Environment trên Render.\n")
    else:
        print("[Boot] Kiểm tra kết nối Supabase...")
        r = supa_get()
        if r is not None:
            print(f"[Boot] ✓ Kết nối OK. Keys: {list(r.keys()) if r else 'rỗng'}")
        else:
            print("[Boot] ✗ Không đọc được — kiểm tra URL/KEY và bảng app_data")
    print(f"[Boot] Lắng nghe port {PORT}\n")
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
