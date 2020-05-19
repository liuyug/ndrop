
import sys
import time
import argparse
import logging
import threading

from . import about
from . import hfs
from .netdrop import NetDropServer, NetDropClient
from .shell import NetDropShell


logger = logging.getLogger(__name__)


def run():
    description = about.description
    epilog = 'NOTE: Output data to STDOUT if "PARM" is "-". ' \
        'To generate new cert/key: ' \
        '"openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 3650"'
    parser = argparse.ArgumentParser(prog=about.name, description=description, epilog=epilog)
    parser.add_argument('-v', '--verbose', action='store_true', help='output debug message')
    parser.add_argument(
        '--version', action='version',
        version='%%(prog)s version %s - written by %s <%s>' % (
            about.version, about.author, about.email),
        help='about')

    group = parser.add_argument_group('Transport Layer Security. TLS/SSL')
    group.add_argument('--cert', metavar='<cert file>', help='cert file.')
    group.add_argument('--key', metavar='<key file>', help='key file.')

    group = parser.add_argument_group('Transport Layer')
    group.add_argument('--listen',
                       metavar='<ip[:tcp_port[:udp_port]]>',
                       help='listen on... '
                       '"tcp_port" is file transfer port. "udp_port" is node message port.')

    group.add_argument('--send',
                       metavar='<ip[:tcp_port]>',
                       help='send to...')

    parser.add_argument(
        'parm', nargs='*',
        metavar='<PARM>',
        help='file, text or directory. On listen mode it is the saved directory. '
    )

    group = parser.add_argument_group('Shell console')
    group.add_argument('--shell',
                       action='store_true',
                       help='Shell console.')

    group = parser.add_argument_group('HTTP File Server')
    group.add_argument('--hfs',
                       action='store_true',
                       help='HTTP Server Address. default: 0.0.0.0:8000')

    group = parser.add_argument_group('Application mode: Dukto, Nitroshare')
    group.add_argument('--mode', choices=['dukto', 'nitroshare'],
                       metavar='<mode>',
                       help='use mode: [dukto, nitroshare]. default: dukto.')

    group.add_argument('--file',
                       action='store_true',
                       help='sent FILE with "dukto" or "nitroshare" mode.')

    group.add_argument('--text',
                       action='store_true',
                       help='sent TEXT with "dukto" mode.')

    args = parser.parse_args()

    app_logger = logging.getLogger(__name__.rpartition('.')[0])
    app_logger.setLevel(logging.INFO)
    if args.verbose:
        app_logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stderr)
    app_logger.addHandler(handler)

    if args.send:
        mode = args.mode or 'dukto'

        client = NetDropClient(args.send, mode=mode, ssl_ck=(args.cert, args.key))
        if args.text:
            client.send_text(' '.join(args.parm))
        else:
            client.send_files(args.parm)
        return

    if args.listen:
        listen = args.listen
    else:
        listen = '0.0.0.0'
    if args.parm:
        saved_dir = args.parm[0]
    else:
        saved_dir = './'
    if ':' in listen and not args.mode:
        parser.error('the following arguments are required: <mode>')

    if args.hfs:
        hfs.start(listen, root_path=saved_dir)
    elif args.shell:
        logging.disable(sys.maxsize)
        shell = NetDropShell()
        server = NetDropServer(listen, mode=args.mode, ssl_ck=(args.cert, args.key))
        server.saved_to(saved_dir)
        threading.Thread(
            name='ndrop server',
            target=server.wait_for_request,
            daemon=True,
        ).start()

        shell._server = server
        shell.cmdloop()
    else:
        server = NetDropServer(listen, mode=args.mode, ssl_ck=(args.cert, args.key))
        server.saved_to(saved_dir)
        server.wait_for_request()


if __name__ == '__main__':
    run()
