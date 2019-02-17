
import io
import sys
import argparse
import logging
import os.path

from tqdm import tqdm
import progressbar

from . import about
from . import dukto


logger = logging.getLogger(__name__)


class NetDrop(object):
    _bar = None
    _transport = None

    def init_bar(self, max_value):
        if logger.getEffectiveLevel() == logging.DEBUG:
            return
        return tqdm(
            total=max_value,
            unit='B', unit_scale=True, unit_divisor=1024,
        )
        widgets = [
            '', progressbar.Percentage(),
            ' ', progressbar.Bar(),
            ' ', progressbar.ETA(),
            ' ', progressbar.FileTransferSpeed(),
        ]
        return progressbar.ProgressBar(widgets=widgets, max_value=max_value).start()


class NetDropServer(NetDrop):
    _file_io = None
    _drop_directory = None

    def __init__(self, addr, mode=None, ssl_ck=None):
        if not mode or mode == 'dukto':
            self._transport = dukto.DuktoServer(self, addr, ssl_ck=ssl_ck)
        else:
            raise ValueError('unknown mode: %s' % mode)
        self._drop_directory = os.path.abspath('./')

    def wait_for_request(self):
        try:
            self._transport.wait_for_request()
        except KeyboardInterrupt:
            self._transport.request_finish()
            print('\n-- Quit --')

    def saved_to(self, path):
        if path == '-':
            self._drop_directory = '-'
            return
        if not os.path.exists(path):
            os.makedirs(path)
        elif not os.path.isdir(path):
            logger.error('File exists: %s !!!' % path)
            return
        self._drop_directory = os.path.abspath(path)

    def recv_feed_file(
            self, path, data, recv_size, file_size, total_recv_size, total_size):
        if not self._file_io:
            if self._drop_directory == '-':
                self._file_io = sys.stdout.buffer
            else:
                name = os.path.join(self._drop_directory, path)
                if not data:
                    if not os.path.exists(name):
                        os.mkdir(name)
                    if not path.endswith(os.sep):
                        path += os.sep
                else:
                    self._file_io = open(name, 'wb')
            if not self._bar:
                self._bar = self.init_bar(total_size)
            logger.debug(path)
            self._bar and self._bar.write(path, file=sys.stderr)
            if not data:
                return

        self._file_io.write(data)
        self._bar and self._bar.update(len(data))

    def recv_finish_file(self, path):
        if self._drop_directory == '-':
            self._file_io.flush()
        else:
            self._file_io.close()
        self._file_io = None

    def request_finish(self):
        if self._bar:
            self._bar.close()
            self._bar = None

    def recv_feed_text(self, data):
        if not self._file_io:
            self._file_io = bytearray()
        self._file_io += data

    def recv_finish_text(self):
        text = self._file_io.decode('utf-8')
        logger.info(text)
        self._file_io = None


class NetDropClient(NetDrop):
    def __init__(self, addr, mode=None, ssl_ck=None):
        if not mode or mode == 'dukto':
            self._transport = dukto.DuktoClient(self, addr, ssl_ck=ssl_ck)
        else:
            raise ValueError('unknown mode: %s' % mode)

    def send_files(self, files):
        all_files = []
        total_size = 0
        for f in files:
            abs_path = os.path.abspath(f)
            base_path = os.path.dirname(abs_path)
            rel_path = os.path.relpath(abs_path, base_path)

            if os.path.isdir(abs_path):
                size = -1
            else:
                size = os.path.getsize(abs_path)
                total_size += size
            all_files.append((abs_path, rel_path, size))

            if size == -1:
                for root, dirs, files in os.walk(abs_path):
                    for name in dirs:
                        sub_abs_path = os.path.join(root, name)
                        rel_path = os.path.relpath(sub_abs_path, base_path)
                        all_files.append((sub_abs_path, rel_path, -1))

                    for name in files:
                        sub_abs_path = os.path.join(root, name)
                        rel_path = os.path.relpath(sub_abs_path, base_path)
                        size = os.path.getsize(sub_abs_path)
                        total_size += size
                        all_files.append((sub_abs_path, rel_path, size))

        self._bar = self.init_bar(total_size)
        self._transport.send_files(total_size, all_files)

    def send_feed_file(self, path, data, send_size, file_size, total_send_size, total_size):
        self._bar and self._bar.update(total_send_size)

    def send_finish_file(self, path):
        self._bar and self._bar.write(path, file=sys.stderr)
        logger.debug(path)

    def send_finish(self):
        if self._bar:
            self._bar.close()
            self._bar = None

    def send_text(self, text):
        logger.info('Send TEXT...')
        self._transport.send_text(text)


def run():
    description=about.description
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-v', '--verbose', action='store_true', help='output more message ')

    parser.add_argument(
        '--cert',
        help='HTTPs cert file. To generate new cert/key: '
        '"openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 3650"'
    )
    parser.add_argument('--key', help='HTTPs key file. To generate new cert/key: see above')
    parser.add_argument('--text', action='store_true', help='FILENAME as TEXT to be send')
    parser.add_argument('--listen', metavar='<IP:PORT>', help='listen to receive FILE')
    parser.add_argument('--send', metavar='<IP:PORT>', help='send FILE')
    parser.add_argument(
        'file', nargs='+', metavar='FILE',
        help='file or directory. On listen mode it is the saved directory. '
        'Will output data to STDOUT if "file" is "-".'
    )

    args = parser.parse_args()

    app_logger = logging.getLogger(__name__.rpartition('.')[0])
    app_logger.setLevel(logging.INFO)
    if args.verbose:
        app_logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stderr)
    app_logger.addHandler(handler)

    if args.listen:
        server = NetDropServer(args.listen, mode='dukto', ssl_ck=(args.cert, args.key))
        server.saved_to(args.file[0])
        server.wait_for_request()
        return
    if args.send:
        client = NetDropClient(args.send, mode='dukto', ssl_ck=(args.cert, args.key))
        if args.text:
            client.send_text(' '.join(args.file))
        else:
            client.send_files(args.file)
        return
    parser.print_help()


if __name__ == '__main__':
    run()
