"""验证真实查询结果的判定边界；不把合成响应当产品验收。"""
import importlib.util
from pathlib import Path
import unittest
import http.server
import json
import tempfile
import threading

SPEC = importlib.util.spec_from_file_location('runtime_queries', Path(__file__).parents[1] / 'query-runtime.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class QueryAssertions(unittest.TestCase):
    def test_counter_instances_are_aggregated_after_independent_series(self):
        rows = [{'metric': {'instance': 'platform-api-1'}, 'value': [1, '6']},
                {'metric': {'instance': 'platform-api-2'}, 'value': [1, '12']}]
        self.assertEqual(MODULE.instance_totals(rows), {'platform-api-1': 6, 'platform-api-2': 12})

    def test_missing_second_instance_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.instance_totals([{'metric': {'instance': 'platform-api-1'}, 'value': [1, '6']}])

    def test_unbounded_instance_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.instance_totals([{'metric': {'instance': 'request-123'}, 'value': [1, '6']}])

    def test_unbounded_label_fails_cardinality_check(self):
        with self.assertRaises(ValueError):
            MODULE.check_labels([{'__name__': 'platform_requests_total', 'trace_id': 'synthetic'}], loki=False)

    def test_three_loki_index_labels_are_allowed(self):
        MODULE.check_labels([{'service_name': 'ontology-platform-api', 'service_version': 'dev',
                              'deployment_environment_name': 'Development'}], loki=True)

    def test_trace_attribute_does_not_count_as_loki_index(self):
        with self.assertRaises(ValueError):
            MODULE.check_labels([{'service_name': 'ontology-platform-api', 'trace_id': 'synthetic'}], loki=True)

    def test_secret_fields_are_redacted_recursively(self):
        self.assertEqual(MODULE.safe_payload({'nested': {'password': 'synthetic-sensitive'}, 'status': 'ok'}),
                         {'nested': {'password': '[REDACTED]'}, 'status': 'ok'})

    def test_remote_or_credential_origin_is_rejected(self):
        for value in ['http://example.com', 'http://user:pass@localhost:15330', 'http://localhost:15330/login']:
            with self.assertRaises(ValueError):
                MODULE.local_origin(value)

    def test_actual_http_success_is_saved_with_method_and_safe_headers(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Set-Cookie', 'synthetic-cookie')
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                origin = 'http://127.0.0.1:' + str(server.server_port)
                capture = MODULE.Capture(Path(directory), 'http://localhost:15330')
                status, body, headers = capture.request('health', origin, '/health')
                self.assertEqual((status, body), (200, {'status': 'ok'}))
                self.assertNotIn('Set-Cookie', headers)
                saved = json.loads((Path(directory) / '001-health.json').read_text())
                self.assertEqual(saved['method'], 'GET')
                self.assertEqual(saved['response'], {'status': 'ok'})
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == '__main__':
    unittest.main()
