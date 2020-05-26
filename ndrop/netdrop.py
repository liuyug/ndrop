
import io
import sys
import argparse
import logging
import os.path
import select
import hashlib

from tqdm import tqdm

from . import dukto
from . import nitroshare


logger = logging.getLogger(__name__)


class NetDrop(object):
    _name = 'Ndrop'
    _bar = None
    _transport = None

    def init_bar(self, max_value):
        if logger.getEffectiveLevel() == logging.DEBUG:
            return
        return tqdm(
            total=max_value,
            unit='B', unit_scale=True, unit_divisor=1024,
        )


class NetDropServer(NetDrop):
    _name = 'NdropServer'
    _transport = None
    _md5 = None
    _file_io = None
    _bar = None
    _drop_directory = None
    _read_only = False
    _nodes = None

    def __init__(self, addr, mode=None, ssl_ck=None):
        self._transport = []
        if not mode or mode == 'dukto':
            self._transport.append(dukto.DuktoServer(self, addr, ssl_ck=ssl_ck))
        if not mode or mode == 'nitroshare':
            self._transport.append(nitroshare.NitroshareServer(self, addr, ssl_ck=ssl_ck))
        self._drop_directory = os.path.abspath('./')
        if not os.access(self._drop_directory, os.W_OK):
            self._read_only = True
            logger.warn('No permission to WRITE: %s' % self._drop_directory)
        self._nodes = {}

    def wait_for_request(self):
        try:
            for transport in self._transport:
                transport.wait_for_request()
            while True:
                r, w, e = select.select(self._transport, [], [], 0.5)
                for transport in self._transport:
                    if transport in r:
                        transport.handle_request()
        except KeyboardInterrupt:
            for transport in self._transport:
                transport.request_finish()
                transport.quit_request()
            logger.info('\n-- Quit --')

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
        if not os.access(self._drop_directory, os.W_OK):
            self._read_only = True
            logger.warn('No permission to WRITE: %s' % self._drop_directory)

    def recv_feed_file(
            self, path, data, recv_size, file_size, total_recv_size, total_size):
        if self._bar is None:   # create process bar for every transfer
            self._bar = self.init_bar(total_size)
        if not self._file_io:  # new file, directory
            if self._drop_directory == '-':
                self._file_io = sys.stdout.buffer
            elif self._read_only:
                logger.warn('No permission WRITING to "%s" and drop it...' % os.path.join(
                    self._drop_directory, path))
            else:
                name = os.path.join(self._drop_directory, path)
                if file_size < 0:    # directory
                    if not os.path.exists(name):
                        os.mkdir(name)
                else:
                    self._file_io = open(name, 'wb')
            if file_size < 0:
                return
            self._md5 = hashlib.md5()  # create md5 for file

        if self._file_io and not self._read_only:
            self._file_io.write(data)
        self._bar.update(len(data))
        self._md5.update(data)

    def recv_finish_file(self, path):
        if self._drop_directory == '-':
            self._file_io.flush()
        else:
            if self._file_io:
                self._file_io.close()
                self._file_io = None
                digest = self._md5.hexdigest()
                self._bar.write('%s  %s' % (digest, path), file=sys.stderr)
                self._md5 = None
            elif self._read_only:
                pass
            else:   # directory
                if not path.endswith(os.sep):
                    path += os.sep
                self._bar.write('%s' % (path), file=sys.stderr)

    def request_finish(self):
        if self._bar is not None:
            self._bar.close()
            self._bar = None

    def recv_feed_text(self, data):
        if not self._file_io:
            self._file_io = io.BytesIO()
        self._file_io.write(data)

    def recv_finish_text(self):
        data = self._file_io.getvalue()
        text = data.decode('utf-8')
        logger.info('TEXT: %s' % text)
        self._file_io.close()
        self._file_io = None

    def get_nodes(self):
        nodes = []
        for transport in self._transport:
            for k, n in transport._nodes.items():
                nodes.append({
                    'mode': transport._name,
                    'ip': k,
                    'port': n['port'],
                    'name': n['name'],
                    'os': n['operating_system'],
                    'format': transport.format_node(n)
                })
        return nodes


class NetDropClient(NetDrop):
    _name = 'NdropClient'
    _transport = None
    _bar = None
    _md5 = None

    def __init__(self, addr, mode=None, ssl_ck=None):
        if mode == 'dukto':
            self._transport = dukto.DuktoClient(self, addr, ssl_ck=ssl_ck)
        elif mode == 'nitroshare':
            self._transport = nitroshare.NitroshareClient(self, addr, ssl_ck=ssl_ck)
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

        # always create process bar
        self._bar = self.init_bar(total_size)
        self._transport.send_files(total_size, all_files)

    def send_feed_file(self, path, data, send_size, file_size, total_send_size, total_size):
        if file_size > -1:
            if not self._md5:  # one md5 every file
                self._md5 = hashlib.md5()
            self._bar.update(len(data))
            self._md5.update(data)

    def send_finish_file(self, path):
        if self._md5:  # file
            digest = self._md5.hexdigest()
            self._md5 = None
            self._bar.write('%s  %s' % (digest, path), file=sys.stderr)
        else:  # directory
            if not path.endswith(os.sep):
                path += os.sep
            self._bar.write('%s' % (path), file=sys.stderr)

    def send_finish(self):
        if self._bar is not None:
            self._bar.close()
            self._bar = None

    def send_text(self, text):
        logger.info('Send TEXT...')
        self._transport.send_text(text)
