
import sys
import argparse
import logging

from . import about
from .netdrop import NetDropServer, NetDropClient


logger = logging.getLogger(__name__)


def run():
    description = about.description
    epilog = 'NOTE: Output data to STDOUT if "FILE" is "-". ' \
        'To generate new cert/key: ' \
        '"openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 3650"'
    parser = argparse.ArgumentParser(prog=about.name, description=description, epilog=epilog)
    parser.add_argument('-v', '--verbose', action='store_true', help='output debug message')
    parser.add_argument(
        '--version', action='version',
        version='%%(prog)s version %s - written by %s <%s>' % (
            about.version, about.author, about.email),
        help='about')

    parser.add_argument('--mode', choices=['dukto', 'nitroshare'], metavar='<mode>',
                        help='protocol mode: [dukto, nitroshare]')
    parser.add_argument('--cert', metavar='<cert file>', help='cert file.')
    parser.add_argument('--key', metavar='<key file>', help='key file.')
    parser.add_argument('--text', action='store_true',
                        help='"FILE" as TEXT to be sent. Only for Dukto')
    parser.add_argument('--listen', metavar='<ip[:tcp_port[:udp_port]]>',
                        help='listen to receive FILE. '
                        '"tcp_port" is file transfer port. "udp_port" is node message port.')
    parser.add_argument('--send', metavar='<ip[:tcp_port]>', help='send FILE.')
    parser.add_argument(
        'file', nargs='+', metavar='FILE',
        help='file or directory. On listen mode it is the saved directory. '
    )

    args = parser.parse_args()

    app_logger = logging.getLogger(__name__.rpartition('.')[0])
    app_logger.setLevel(logging.INFO)
    if args.verbose:
        app_logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stderr)
    app_logger.addHandler(handler)

    if args.listen:
        if ':' in args.listen and not args.mode:
            parser.error('the following arguments are required: <mode>')
        server = NetDropServer(args.listen, mode=args.mode, ssl_ck=(args.cert, args.key))
        server.saved_to(args.file[0])
        server.wait_for_request()
        return
    if args.send:
        if not args.mode:
            parser.error('Error: the following arguments are required: <mode>')
        client = NetDropClient(args.send, mode=args.mode, ssl_ck=(args.cert, args.key))
        if args.text:
            client.send_text(' '.join(args.file))
        else:
            client.send_files(args.file)
        return
    parser.print_help()


if __name__ == '__main__':
    run()
