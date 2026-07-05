"""로컬 정적 서버 — docs/ 를 서빙한다. (샌드박스 환경에서 os.getcwd() 접근이 막혀 있어
`python -m http.server`의 argparse 초기화가 실패하는 문제를 피하기 위해 직접 구현)
"""

import http.server
import socketserver

PORT = 8765
DIRECTORY = "/Users/hyunseojang/Projects/산업 스터디/docs"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    with ReusableTCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()
