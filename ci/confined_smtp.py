"""Disposable SMTP sink with an in-memory receipt API; never forwards mail."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import StreamRequestHandler, ThreadingTCPServer
from threading import Thread, Lock

MESSAGES = []
LOCK = Lock()


class SMTP(StreamRequestHandler):
    def handle(self):
        sender, recipients = "", []
        self.wfile.write(b"220 fictional confined SMTP\r\n")
        while line := self.rfile.readline(4096):
            command = line.decode("utf-8", "replace").strip()
            upper = command.upper()
            if upper.startswith(("EHLO", "HELO")):
                response = b"250-fictional confined SMTP\r\n250 SIZE 262144\r\n"
            elif upper.startswith("MAIL FROM:"):
                sender, recipients = command[10:].strip(), []
                response = b"250 sender accepted\r\n"
            elif upper.startswith("RCPT TO:"):
                address = command[8:].strip()
                if ".invalid" not in address.lower() or "reject." in address.lower():
                    response = b"550 fictional controlled recipient rejection\r\n"
                else:
                    recipients.append(address)
                    response = b"250 recipient accepted\r\n"
            elif upper == "DATA":
                if not recipients:
                    response = b"554 no confined recipient\r\n"
                else:
                    self.wfile.write(b"354 send message\r\n")
                    body = bytearray()
                    while chunk := self.rfile.readline(262145):
                        if chunk == b".\r\n":
                            break
                        body.extend(chunk[1:] if chunk.startswith(b"..") else chunk)
                        if len(body) > 262144:
                            return
                    with LOCK:
                        MESSAGES.append({"from": sender, "to": recipients[:], "data": body.decode("utf-8", "replace")})
                    response = b"250 retained in confined memory\r\n"
            elif upper == "RSET":
                sender, recipients = "", []
                response = b"250 reset\r\n"
            elif upper == "QUIT":
                self.wfile.write(b"221 closed\r\n")
                return
            else:
                response = b"250 OK\r\n"
            self.wfile.write(response)


class Receipts(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 -- native HTTPServer method name.
        if self.path != "/messages":
            self.send_error(404)
            return
        with LOCK:
            data = json.dumps({"count": len(MESSAGES), "messages": MESSAGES}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format, *args):
        return


class Sink(ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    Thread(target=ThreadingHTTPServer(("0.0.0.0", 8025), Receipts).serve_forever, daemon=True).start()
    with Sink(("0.0.0.0", 2525), SMTP) as smtp:
        smtp.serve_forever()
