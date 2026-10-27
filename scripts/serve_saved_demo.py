"""View/record the published browser demo; stdlib only, no model or SUMO calls."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from trafficlab.security import trusted_browser_request

FILES={
    '/': ('trafficlab/static/demo.html','text/html; charset=utf-8'),
    '/demo': ('trafficlab/static/demo.html','text/html; charset=utf-8'),
    '/demo.js': ('trafficlab/static/demo.js','text/javascript; charset=utf-8'),
    '/demo-data.json': ('data/published/traffic-objective-v2/replays.json','application/json'),
    '/demo-results.png': ('media/02-before-after-results.png','image/png'),
}
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        super().end_headers()
    def do_GET(self):
        if not trusted_browser_request(self.headers, self.server.server_port):
            self.send_error(403); return
        item=FILES.get(urlsplit(self.path).path)
        if item is None or not (ROOT/item[0]).is_file(): self.send_error(404); return
        body=(ROOT/item[0]).read_bytes()
        self.send_response(200); self.send_header('Content-Type',item[1]); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--port',type=int,default=8766); args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Saved demo: http://127.0.0.1:{args.port}/ (no paid endpoints)',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
