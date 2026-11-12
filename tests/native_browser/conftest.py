"""Real localhost TCP forwarding for Chromium secure-context storage APIs."""
import select
import socket
import socketserver
import threading

import pytest


class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.create_connection(('webui', 8080), timeout=10) as upstream:
            peers=(self.request,upstream)
            while True:
                ready,_,_=select.select(peers,[],[],30)
                if not ready:
                    return
                for source in ready:
                    data=source.recv(65536)
                    if not data:
                        return
                    (upstream if source is self.request else self.request).sendall(data)


@pytest.fixture(scope='session',autouse=True)
def localhost_native_transport():
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address=True
        daemon_threads=True
    server=Server(('127.0.0.1',8080),Forward)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    yield
    server.shutdown(); server.server_close(); worker.join()