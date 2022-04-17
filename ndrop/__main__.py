
import os
import sys
import time
import argparse
import logging
import threading
import glob

from . import about
from . import hfs
from .netdrop import NetDropServer, NetDropClient


logger = logging.getLogger(__name__)


def run():
    description = '%s\n%s' % (about.description, about.detail)
    epilog = 'NOTE: Output data to STDOUT if "PARAM" is "-". ' \
        'To generate new cert/key: ' \
        '"openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 3650"'
    parser = argparse.ArgumentParser(prog=about.name, description=description, epilog=epilog)
    parser.add_argument('-v', '--verbose', action='store_true', help='output debug message')
    parser.add_argument(
        '--version', action='version',
        version=about.banner,
        help='about')

    parser.add_argument(
        '--gui-tk', action='store_true', help='run with GUI Tkinter')
    parser.add_argument(
        '--gui', action='store_true', help='run with GUI Kivy')

    group = parser.add_argument_group('Transport Layer Security. TLS/SSL')
    group.add_argument('--cert', metavar='<cert file>', help='cert file.')
    group.add_argument('--key', metavar='<key file>', help='key file.')

    group = parser.add_argument_group('Transport Layer')
    group.add_argument('--listen',
                       metavar='<ip[:port]>',
                       help='listen on...')

    group.add_argument('--send',
                       metavar='<ip[:port]>',
                       help='send to...')

    parser.add_argument(
        'param', nargs='*',
        metavar='<PARAM>',
        help='file, text or directory. refer to other option'
    )

    group = parser.add_argument_group('HTTP File Server')
    group.add_argument('--hfs',
                       action='store_true',
                       help='start HTTP File Server.'
                       ' use "--listen" to change server address.'
                       ' "PARAM" is root path.')

    group = parser.add_argument_group('Application Layer Mode: Dukto, Nitroshare')
    group.add_argument('--mode', choices=['dukto', 'nitroshare'],
                       metavar='<mode>',
                       help='application mode: [dukto, nitroshare]. default: dukto.')

    group.add_argument('--file',
                       action='store_true',
                       help='sent FILE with "dukto" or "nitroshare" mode.'
                       ' "PARAM" is files')

    group.add_argument('--text',
                       action='store_true',
                       help='sent TEXT with "dukto" mode.'
                       ' "PARAM" is message')

    args = parser.parse_args()

    if args.gui_tk:
        from .__main_tk__ import run as run_gui
        run_gui()
        return
    if args.gui:
        os.environ['KIVY_NO_ARGS'] = '1'
        from .__main_kivy__ import run as run_gui
        run_gui()
        return

    app_logger = logging.getLogger(__name__.rpartition('.')[0])
    app_logger.setLevel(logging.INFO)
    if args.verbose:
        app_logger.setLevel(logging.DEBUG)

    FORMAT = ' * %(message)s'
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=FORMAT))
    app_logger.addHandler(handler)

    print(about.banner)
    if args.send:
        mode = args.mode or 'dukto'
        client = NetDropClient(args.send, mode=mode, ssl_ck=(args.cert, args.key))
        if args.text:
            client.send_text(' '.join(args.param))
        else:
            params = []
            for p in args.param:
                params.extend(glob.glob(p))
            client.send_files(params)
        return

    if args.listen:
        listen = args.listen
    else:
        listen = '0.0.0.0'
    if args.param:
        saved_dir = args.param[0]
    else:
        saved_dir = './'
    if ':' in listen and not args.mode:
        parser.error('the following arguments are required: <mode>')

    if args.hfs:
        hfs.start(listen, root_path=saved_dir, cert=args.cert, key=args.key)
    else:
        logger.info('File Transfer Server start (Press CTRL+C to quit)')
        server = NetDropServer(listen, mode=args.mode, ssl_ck=(args.cert, args.key))
        server.saved_to(saved_dir)
        server.wait_for_request()


if __name__ == '__main__':
    run()
