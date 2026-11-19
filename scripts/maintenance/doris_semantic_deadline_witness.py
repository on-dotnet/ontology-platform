"""仅在正式期限见证时转发本机验证图 HTTP，观测真实 DELETE 与响应断开。"""
import contextlib
import http.client
import http.server
import json
import re
import select
import socket
import threading
import time
from urllib.parse import parse_qs, urlsplit


@contextlib.contextmanager
def validation_origin(output, run_id):
    """分配回环端口；只持有此运行自己成功 PUT 的精确图，结束前逐图对账。"""
    activation = output / ('root-arm-' + run_id + '.json')
    evidence = output / ('root-dependencies-' + run_id + '.json')
    events = []
    owned = set()
    lock = threading.Lock()

    def event(phase, kind, path, **details):
        with lock:
            events.append(dict(phase=phase, kind=kind, path=path, utcNs=time.time_ns(), **details))

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def forward(self):
            uri = urlsplit(self.path)
            graph = parse_qs(uri.query).get('graph', [''])[0]
            if (uri.path not in ('/validation/data', '/validation/shacl') or
                    not re.fullmatch(r'urn:ontology-platform:temporary:[0-9a-f]{32}', graph) or
                    self.command not in (('POST',) if uri.path.endswith('/shacl') else ('PUT', 'GET', 'DELETE'))):
                self.send_error(400)
                return
            phase = json.loads(activation.read_bytes()) if activation.exists() else None
            if phase not in (None, 'query', 'cancel'):
                self.send_error(400)
                return
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 8 * 1024 * 1024:
                self.send_error(413)
                return
            with lock:
                if self.command == 'PUT':
                    owned.add(self.path)
                elif uri.path.endswith('/data') and self.path not in owned:
                    self.send_error(400)
                    return
            headers = {key: self.headers[key] for key in ('Content-Type', 'Accept') if key in self.headers}
            with contextlib.closing(http.client.HTTPConnection('127.0.0.1', 15645, timeout=2)) as upstream:
                upstream.request(self.command, self.path, self.rfile.read(size) if size else None, headers)
                response = upstream.getresponse()
                data = response.read(8 * 1024 * 1024 + 1)
                if len(data) > 8 * 1024 * 1024:
                    self.send_error(502)
                    return
                if phase:
                    event(phase, self.command, self.path, status=response.status)
                if phase and self.command == 'DELETE' and response.status in (200, 204, 404):
                    # 真实 DELETE 已返回；仅精确这次响应尚未传回产品。观察客户端传输结束。
                    if select.select([self.connection], [], [], 5.2)[0] and not self.connection.recv(1, socket.MSG_PEEK):
                        event(phase, 'client_closed', self.path)
                        return
                    event(phase, 'safety_release', self.path)
                self.send_response(response.status)
                self.send_header('Content-Type', response.getheader('Content-Type', 'text/plain'))
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        do_GET = do_PUT = do_POST = do_DELETE = forward

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = False
        block_on_close = True

    with Server(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            yield 'http://127.0.0.1:' + str(server.server_port) + '/validation'
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
            # 只删除本见证在正式 HTTP 中登记的准确 IRI；404 也须单独 GET 证实。
            for path in sorted(owned):
                with contextlib.closing(http.client.HTTPConnection('127.0.0.1', 15645, timeout=2)) as client:
                    for method in ('DELETE', 'GET'):
                        client.request(method, path)
                        reply = client.getresponse()
                        reply.read()
                        event('restore', method, path, status=reply.status)
            with evidence.open('x') as stream:
                json.dump(events, stream, indent=2)
                stream.write('\n')
