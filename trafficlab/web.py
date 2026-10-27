"""Local browser replay of positions emitted by real SUMO/TraCI runs."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit

from .controllers import make_controller
from .benchmark.problem import CURRENT_OBJECTIVE, fingerprint
from .benchmark.reference import REFERENCE_VERSION
from .metrics import add_evaluation
from .openrouter import DECISION_MODELS, PROMPT_VERSION, prompt_sha256
from .sol import SOL_MODEL
from .runner import run_episode
from .scenario import Config, ROOT
from .security import trusted_browser_request


PAGE = Path(__file__).parent / "static" / "replay.html"
SCRIPT = Path(__file__).parent / "static" / "replay.js"
CACHE_VERSION = 2
PLANNING_MODEL_CACHE_VERSION = 4


def cache_path(controller_name: str, config: Config) -> Path:
    if controller_name not in {"fixed", "adaptive", "gurobi", "sol-medium", *DECISION_MODELS}:
        raise ValueError("unknown controller")
    if controller_name in DECISION_MODELS or controller_name == "sol-medium":
        model = SOL_MODEL if controller_name == "sol-medium" else DECISION_MODELS[controller_name]
        version = f"{PLANNING_MODEL_CACHE_VERSION}:{PROMPT_VERSION}:{prompt_sha256(config.planning_horizon)}:{model}"
    else:
        version = PLANNING_MODEL_CACHE_VERSION if controller_name == "gurobi" else CACHE_VERSION
    # CLI/programmatic callers may supply 120 while HTTP supplies 120.0.
    # Equivalent numeric settings must address the same recording.
    canonical_config = {name: float(value) if Config.__dataclass_fields__[name].type is float else value
                        for name, value in config.record().items()}
    identity = {"version": version, "controller": controller_name, "config": canonical_config,
                "objective": fingerprint(CURRENT_OBJECTIVE.__dict__), "reference_version": REFERENCE_VERSION}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    return ROOT / "results" / "web-cache" / f"{controller_name}_{digest}" / "replay.json"


def cached_episode(controller_name: str, config: Config, saved_only: bool = False) -> dict:
    trace_path = cache_path(controller_name, config)
    if trace_path.is_file():
        valid = False
        try:
            data = json.loads(trace_path.read_text(encoding="utf-8"))
            valid = data["result"]["controller"] == controller_name and data["result"]["config"] == config.record()
        except (ValueError, KeyError, TypeError):
            pass
        if valid:
            if controller_name in {'gurobi', 'sol-medium', *DECISION_MODELS} and data['result'].get('planning_objective') != CURRENT_OBJECTIVE.__dict__:
                raise ValueError('Saved replay uses a different planning objective; no automatic rerun was started.')
            # An accounting error must not silently trigger another paid run.
            data["result"] = add_evaluation(data["result"])
            return dict(data, cache_hit=True)
    if saved_only:
        raise ValueError("This replay is not available yet. No new simulation or model call was started.")
    controller = make_controller(controller_name, horizon=config.planning_horizon)
    run_episode(config, controller, output_dir=trace_path.parent, trace_file=trace_path)
    return dict(json.loads(trace_path.read_text(encoding="utf-8")), cache_hit=False)


class Handler(BaseHTTPRequestHandler):
    run_lock = threading.Lock()

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        super().end_headers()

    def trusted_request(self):
        if trusted_browser_request(self.headers, self.server.server_port):
            return True
        self.respond(403, {"error": "Only same-origin localhost requests are allowed"})
        return False

    def log_message(self, format, *args):
        return

    def respond(self, code: int, data: dict):
        body = json.dumps(data, allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.trusted_request():
            return
        path = urlsplit(self.path).path
        demo_files = {
            '/demo': (PAGE.parent / 'demo.html', 'text/html; charset=utf-8'),
            '/demo.js': (PAGE.parent / 'demo.js', 'text/javascript; charset=utf-8'),
            '/demo-data.json': (ROOT / 'data/published/traffic-objective-v2/replays.json', 'application/json'),
            '/demo-results.png': (ROOT / 'media/02-before-after-results.png', 'image/png'),
        }
        if path == "/":
            body, content_type = PAGE.read_bytes(), "text/html; charset=utf-8"
        elif path == "/replay.js":
            body, content_type = SCRIPT.read_bytes(), "text/javascript; charset=utf-8"
        elif path in demo_files and demo_files[path][0].is_file():
            source, content_type = demo_files[path]
            body = source.read_bytes()
        else:
            self.respond(404, {"error": "not found"})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.trusted_request():
            return
        if urlsplit(self.path).path != "/api/generate":
            self.respond(404, {"error": "not found"})
            return
        if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
            self.respond(415, {"error": "Use an application/json request with Content-Length"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("invalid request length")
            values = json.loads(self.rfile.read(length))
            if not isinstance(values, dict):
                raise ValueError("request must be a JSON object")
            controller_name = str(values.get("controller", "fixed"))
            config = Config(seed=int(values.get("seed", 7)),
                            duration=float(values.get("duration", 120)),
                            planning_horizon=values.get("horizon", 15),
                            inflow_per_approach=float(values.get("inflow", 0.15)),
                            cav_share=float(values.get("cav_share", 0.5)))
            if config.duration > 600:
                raise ValueError("browser replays are limited to 600 simulated seconds")
            if not self.run_lock.acquire(blocking=False):
                self.respond(409, {"error": "A simulation is already running"})
                return
            try:
                data = cached_episode(controller_name, config, saved_only=values.get("saved_only") is True)
            finally:
                self.run_lock.release()
            self.respond(200, data)
        except (ValueError, TypeError, KeyError, OverflowError):
            self.respond(400, {"error": "Invalid request or unavailable saved replay; check the selected settings"})
        except Exception:
            # Provider/solver exceptions may contain account data or local paths.
            self.respond(500, {"error": "Simulation could not complete; check the local configuration and provider access"})


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("browser replay binds only to localhost")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"SUMO replay: http://{host}:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
