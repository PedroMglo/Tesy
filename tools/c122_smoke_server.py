"""Harmless two-request server that reports the trace trigger state."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import signal
import sys


class Handler(BaseHTTPRequestHandler):
    def respond(self, row):
        data = json.dumps(row).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/health': self.respond({'status':'ok'})
        elif self.path == '/v1/models': self.respond({'data':[{'id':'c122-smoke'}]})
        else: self.send_error(404)

    def do_POST(self):
        if self.path != '/v1/chat/completions':
            self.send_error(404); return
        row = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        prompt = row['messages'][-1]['content']
        present = os.path.exists(os.environ['TESY_C122_TRACE_TRIGGER_FILE'])
        content = ('PRESENT' if present else 'ABSENT') if prompt in ('first','second') else 'BAD'
        self.respond({'choices':[{'message':{'role':'assistant','content':content},
                                  'finish_reason':'stop'}],
                      'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2},
                      'timings':{'cache_n':0,'prompt_n':1,'predicted_n':1,
                                 'prompt_ms':1,'predicted_ms':1}})

    def log_message(self,*_): pass


if __name__ == '__main__':
    server=HTTPServer(('127.0.0.1',18367),Handler)
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
    server.serve_forever()
