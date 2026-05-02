#!/usr/bin/env python3
"""Local HTTP server with Range request support (required for PMTiles)."""
import os
import re
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler


class RangeHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        range_header = self.headers.get("Range")
        if not range_header:
            super().do_GET()
            return

        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            super().do_GET()
            return

        file_size = os.path.getsize(path)
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not m:
            super().do_GET()
            return

        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        try:
            with open(path, "rb") as f:
                f.seek(start)
                data = f.read(length)
        except OSError:
            self.send_error(500)
            return

        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.end_headers()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    server = HTTPServer(("", port), RangeHTTPRequestHandler)
    print(f"Serving at http://localhost:{port}/")
    print(f"Map:       http://localhost:{port}/map/")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
