"""Serve the frontend on port 5353."""
import http.server
import os

PORT = 5353
DIR = os.path.join(os.path.dirname(__file__), "public")

os.chdir(DIR)
handler = http.server.SimpleHTTPRequestHandler

with http.server.HTTPServer(("", PORT), handler) as httpd:
    print(f"Frontend running at http://localhost:{PORT}")
    httpd.serve_forever()
