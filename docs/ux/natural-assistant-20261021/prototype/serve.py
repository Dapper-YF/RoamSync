"""Serve this prototype only on localhost; no project API is proxied."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from functools import partial
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=3087)
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
class PrototypeHandler(SimpleHTTPRequestHandler):
    # Windows registry may map .mjs to text/plain, which browsers reject for modules.
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript'}

handler = partial(PrototypeHandler, directory=str(root))
print(f'Prototype: http://localhost:{args.port}/prototype/', flush=True)
ThreadingHTTPServer(('127.0.0.1', args.port), handler).serve_forever()
