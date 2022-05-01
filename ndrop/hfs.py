import os
import socket
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
import threading
import logging

from .about import banner
from .transport import get_broadcast_address


logger = logging.getLogger(__name__)


class Handler(SimpleHTTPRequestHandler):
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except Exception as err:
            logger.warn('%s - - [%s] %s' % (
                self.client_address[0],
                self.log_date_time_string(),
                err,
            ))

    def log_message(self, format, *args):
        message = "%s - - [%s] %s" % (
            self.client_address[0],
            self.log_date_time_string(),
            format % args)
        logger.info(message)


class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    pass


def start(listen, root_path=None, cert=None, key=None, daemon=False):
    if listen:
        ip, _, port = listen.partition(':')
        port = int(port) if port else 8000
    else:
        ip = '0.0.0.0'
        port = 8000

    root_path = root_path or './'
    os.chdir(root_path)

    server = ThreadingSimpleServer((ip, port), Handler)
    if cert and key:
        import ssl
        server.socket = ssl.wrap_socket(
            server.socket,
            keyfile=key, certfile=cert,
            server_side=True)
        proto = 'https'
    else:
        proto = 'http'

    try:
        logger.info('HTTP File Server start')
        logger.info('Running on %s://%s:%s/ (Press CTRL+C to quit)' % (proto, ip, port))
        if ip == '0.0.0.0':
            ipaddrs, boradcasts = get_broadcast_address()
            logger.info('visit site: %s' % ', '.join(['%s://%s:%s' % (proto, ipaddr, port) for ipaddr in ipaddrs]))
        logger.info('Root path: %s' % root_path)
        if daemon:
            threading.Thread(
                name='HFS server',
                target=server.serve_forever,
                daemon=True,
            ).start()
        else:
            # main thread
            server.serve_forever()
    except KeyboardInterrupt:
        print('\n-- Quit --')
    return server
