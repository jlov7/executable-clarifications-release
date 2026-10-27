"""Build and serve only the static research UI on literal loopback."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from build_session_demo import verify_assets


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    if not 1<=args.port<=65535: parser.error('port must be 1..65535')
    web=Path(__file__).resolve().parents[1]/'web'
    verify_assets()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(SimpleHTTPRequestHandler,directory=str(web)))
    print(f'http://127.0.0.1:{server.server_port}/session.html',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__=='__main__':main()
