"""Offline regression checks for publication and paid-request boundaries."""

from email.message import Message
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request
import zipfile

from scripts.check_publication_security import inspect_bytes
from trafficlab.openrouter import OpenRouterDecisions
from trafficlab.metrics import evaluate_demand
from defusedxml.common import DefusedXmlException
from trafficlab.security import NoCredentialRedirect, open_api_request
from trafficlab.sol import SolMediumReasoning
from trafficlab.web import Handler


def handler(payload=None, host="127.0.0.1:8765", origin=None, content_type="application/json"):
    value = object.__new__(Handler)
    value.server = SimpleNamespace(server_port=8765)
    value.path = "/api/generate"
    value.headers = Message()
    value.headers["Host"] = host
    if origin is not None:
        value.headers["Origin"] = origin
    raw = json.dumps(payload if payload is not None else {"controller": "gurobi", "saved_only": True}).encode()
    value.headers["Content-Type"] = content_type
    value.headers["Content-Length"] = str(len(raw))
    value.rfile = io.BytesIO(raw)
    value.respond = Mock()
    return value


class BrowserBoundaryTests(unittest.TestCase):
    def test_cross_origin_and_rebound_hosts_never_reach_simulation(self):
        for host, origin in (("attacker.invalid:8765", None),
                             ("127.0.0.1:8765", "https://attacker.invalid"),
                             ("127.0.0.1:8765", "null"),
                             ("localhost:8765", "http://127.0.0.1:8765")):
            with self.subTest(host=host, origin=origin), patch("trafficlab.web.cached_episode") as run:
                value = handler(host=host, origin=origin)
                value.do_POST()
                self.assertEqual(value.respond.call_args.args[0], 403)
                run.assert_not_called()

    def test_simple_cross_origin_content_types_cannot_start_paid_work(self):
        for kind in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
            with self.subTest(kind=kind), patch("trafficlab.web.cached_episode") as run:
                value = handler(content_type=kind)
                value.do_POST()
                self.assertEqual(value.respond.call_args.args[0], 415)
                run.assert_not_called()

    def test_malformed_and_oversized_bodies_do_not_start_work(self):
        for payload in ([], None):
            with patch("trafficlab.web.cached_episode") as run:
                value = handler(payload=payload)
                if payload is None:
                    value.headers.replace_header("Content-Length", "4097")
                value.do_POST()
                self.assertEqual(value.respond.call_args.args[0], 400)
                run.assert_not_called()

    def test_same_origin_saved_request_still_loads(self):
        with patch("trafficlab.web.cached_episode", return_value={"cache_hit": True}) as run:
            value = handler(origin="http://127.0.0.1:8765")
            value.do_POST()
            self.assertEqual(value.respond.call_args.args, (200, {"cache_hit": True}))
            self.assertTrue(run.call_args.kwargs["saved_only"])

    def test_run_queue_is_bounded_and_errors_do_not_expose_details(self):
        with patch("trafficlab.web.cached_episode") as run:
            value = handler()
            with Handler.run_lock:
                value.do_POST()
            self.assertEqual(value.respond.call_args.args[0], 409)
            run.assert_not_called()
        with patch("trafficlab.web.cached_episode", side_effect=RuntimeError("private account detail")):
            value = handler()
            value.do_POST()
            self.assertEqual(value.respond.call_args.args[0], 500)
            self.assertNotIn("private account detail", json.dumps(value.respond.call_args.args))
            self.assertFalse(Handler.run_lock.locked())


class CredentialBoundaryTests(unittest.TestCase):
    def test_authenticated_requests_do_not_follow_redirects(self):
        request = Request("https://openrouter.ai/api/alpha/decisions")
        with self.assertRaises(HTTPError):
            NoCredentialRedirect().redirect_request(request, None, 302, "redirect", {}, "https://attacker.invalid/")
        for url in ("http://openrouter.ai/", "https://attacker.invalid/", "https://openrouter.ai.attacker.invalid/"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                open_api_request(Request(url), timeout=1)

    def test_provider_error_bodies_and_network_details_are_not_exposed(self):
        for cls, module in ((OpenRouterDecisions, "trafficlab.openrouter"),
                            (SolMediumReasoning, "trafficlab.sol")):
            for error in (HTTPError("https://openrouter.ai/", 401, "private account detail", {}, io.BytesIO(b'private account detail')),
                          URLError("private account detail")):
                with self.subTest(cls=cls, error=type(error)), patch(module + ".urlopen", side_effect=error):
                    with self.assertRaises(RuntimeError) as caught:
                        cls(api_key="unit-test")._post({})
                    self.assertNotIn("private account detail", str(caught.exception))


class PublicationBoundaryTests(unittest.TestCase):
    def test_xml_readers_reject_entity_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demand.xml"
            path.write_text('<!DOCTYPE routes [<!ENTITY example "expanded">]><routes>&example;</routes>')
            with self.assertRaises(DefusedXmlException):
                evaluate_demand(path, Path(directory) / "trips.xml", 120)

    def test_scanner_reads_archives_and_reports_only_locations(self):
        secret = b"generated-fixture-only-key-value"
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("notes.txt", secret)
            archive.writestr("../outside.txt", b"example")
        findings = inspect_bytes("snapshot.zip", stream.getvalue(), [secret])
        self.assertIn(("snapshot.zip!notes.txt", "configured local secret"), findings)
        self.assertIn(("snapshot.zip!../outside.txt", "private or unsafe publication path"), findings)
        self.assertNotIn(secret.decode(), repr(findings))

    def test_scanner_detects_private_paths_without_publishing_fixture_details(self):
        private_path = ("/" + "Users" + "/" + "example-user" + "/" + "work").encode()
        self.assertIn(("network.xml", "personal filesystem path"), inspect_bytes("network.xml", private_path))
        self.assertEqual(inspect_bytes(".env.example", b"OPENROUTER_API_KEY=\n"), [])


if __name__ == "__main__":
    unittest.main()
