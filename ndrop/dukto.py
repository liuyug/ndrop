
import logging
import os.path

import socket
import socketserver
import ssl

from .transport import Transport


logger = logging.getLogger(__name__)


CHUNK_SIZE = 1024 * 10
DEFAULT_UDP_PORT = 4644
DEFAULT_TCP_PORT = 4644
TEXT_TAG = '___DUKTO___TEXT___'

STATUS = {
    'idle': 0,
    'filename': 1,
    'filesize': 2,
    'data': 3,
}


class DuktoPacket():
    _status = STATUS['idle']
    _record = 0
    _recv_record = 0
    _total_size = 0
    _total_recv_size = 0
    _filename = None
    _filesize = 0
    _recv_file_size = 0

    def get_system_signature():
        signature = '%s at %s (%s)' % ('test_user', 'test_host', 'test_platform')
        return signature

    def pack_text(self, text):
        data = bytearray()
        total_size = size = len(text)
        record = 1
        data.extend(record.to_bytes(8, byteorder='little', signed=True))
        data.extend(total_size.to_bytes(8, byteorder='little', signed=True))

        data.extend(TEXT_TAG.encode())
        data.append(0x00)
        data.extend(size.to_bytes(8, byteorder='little', signed=True))

        data.extend(text.encode('utf-8'))
        return data

    def pack_files_header(self, count, total_size):
        data = bytearray()
        data.extend(count.to_bytes(8, byteorder='little', signed=True))
        data.extend(total_size.to_bytes(8, byteorder='little', signed=True))
        return data

    def pack_files(self, agent, total_size, files):
        data = bytearray()
        total_send_size = 0
        for path, name, size in files:
            data.clear()
            data.extend(name.encode('utf-8'))
            data.append(0x00)
            data.extend(size.to_bytes(8, byteorder='little', signed=True))
            yield data
            if size > 0:
                send_size = 0
                with open(path, 'rb') as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        send_size += len(chunk)
                        total_send_size += len(chunk)
                        agent.send_feed_file(
                            name, chunk,
                            send_size, size, total_send_size, total_size,
                        )
                        yield chunk
            agent.send_finish_file(name)

    def unpack(self, agent, data):
        while len(data) > 0:
            if self._status == STATUS['idle']:
                value = data[:8]
                del data[:8]
                self._record = int.from_bytes(value, byteorder='little', signed=True)
                self._recv_record = 0
                value = data[:8]
                del data[:8]
                self._total_size = int.from_bytes(value, byteorder='little', signed=True)
                self._total_recv_size = 0
                self._status = STATUS['filename']
            elif self._status == STATUS['filename']:
                pos = data.find(b'\0', 0)
                if pos < 0:
                    return
                value = data[:pos]
                del data[:pos + 1]
                self._filename = value.decode('utf-8')
                self._status = STATUS['filesize']
            elif self._status == STATUS['filesize']:
                if len(data) < 8:
                    return
                value = data[:8]
                del data[:8]
                self._filesize = int.from_bytes(value, byteorder='little', signed=True)
                self._recv_file_size = 0
                if self._filesize == -1:
                    agent.recv_directory('%s%s' % (self._filename, os.sep))
                    self._status = STATUS['filename']
                else:
                    self._status = STATUS['data']
            elif self._status == STATUS['data']:
                size = min(self._filesize - self._recv_file_size, len(data))
                self._recv_file_size += size
                self._total_recv_size += size

                agent.recv_feed_file(
                    self._filename, data[:size],
                    self._recv_file_size, self._filesize,
                    self._total_recv_size, self._total_size,
                )
                del data[:size]

                if self._recv_file_size == self._filesize:
                    self._status = STATUS['filename']
                    self._recv_record += 1
                    agent.recv_finish_file(self._filename)
                if self._total_recv_size == self._total_size:
                    self._status = STATUS['idle']
                    data.clear()


class ServerHander(socketserver.BaseRequestHandler):
    def setup(self):
        self._packet = DuktoPacket()
        self._recv_buff = bytearray()

    def handle(self):
        logger.info('connect from %s:%s' % self.client_address)
        while True:
            data = self.request.recv(CHUNK_SIZE)
            if not data:
                break
            self._recv_buff.extend(data)
            self._packet.unpack(self.server.agent, self._recv_buff)

    def finish(self):
        self.server.agent.request_finish()


class DuktoServer(Transport):
    _cert = None
    _key = None
    _owner = None
    _server = None
    _packet = None
    _data = None

    def __init__(self, owner, addr, ssl_ck=None):
        if ssl_ck:
            self._cert, self._key = ssl_ck
        self._owner = owner
        self._data = bytearray()
        if ':' in addr:
            ip, port = addr.split(':')
            port = int(port)
        else:
            ip = addr
            port = DEFAULT_TCP_PORT
        address = (ip, port)
        self._server = socketserver.TCPServer((ip, port), ServerHander)
        if self._cert and self._key:
            self._server.socket = ssl.wrap_socket(
                self._server.socket,
                keyfile=self._key, certfile=self._cert, server_side=True)
        self._server.agent = self

    def get_network_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.connect(('<broadcast>', 0))
        return s.getsockname()[0]

    def wait_for_request(self):
        addr = self.get_network_ip()
        logger.info('listen on %s:%s' % (addr, self._server.server_address[1]))
        self._server.serve_forever()

    def recv_feed_file(self, path, data, recv_size, file_size, total_recv_size, total_size):
        if path == TEXT_TAG:
            self._owner.recv_feed_text(data)
        else:
            self._owner.recv_feed_file(
                path, data, recv_size, file_size, total_recv_size, total_size)

    def recv_finish_file(self, path):
        if path == TEXT_TAG:
            self._owner.recv_finish_text()
        else:
            self._owner.recv_finish_file(path)

    def request_finish(self):
        self._owner.request_finish()

    def recv_directory(self, path):
        self._owner.recv_directory(path)


class DuktoClient(Transport):
    _cert = None
    _key = None
    _owner = None
    _packet = None

    def __init__(self, owner, addr, ssl_ck=None):
        if ssl_ck:
            self._cert, self._key = ssl_ck
        self._owner = owner
        if ':' in addr:
            ip, port = addr.split(':')
            port = int(port)
        else:
            ip = addr
            port = DEFAULT_TCP_PORT
        self._address = (ip, port)
        self._packet = DuktoPacket()

    def send_text(self, text):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self._cert and self._key:
            sock = ssl.wrap_socket(
                sock,
                keyfile=self._key, certfile=self._cert, server_side=False)
        sock.connect(self._address)
        data = self._packet.pack_text(text)
        try:
            sock.sendall(data)
        except KeyboardInterrupt:
            pass
        except Exception:
            pass
        sock.close()
        self.send_finish()

    def send_files(self, total_size, files):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self._cert and self._key:
            sock = ssl.wrap_socket(
                sock,
                keyfile=self._key, certfile=self._cert, server_side=False)
        sock.connect(self._address)
        header = self._packet.pack_files_header(len(files), total_size)
        try:
            sock.sendall(header)
            for chunk in self._packet.pack_files(self, total_size, files):
                sock.sendall(chunk)
        except KeyboardInterrupt:
            pass
        except Exception:
            pass
        sock.close()
        self.send_finish()

    def send_feed_file(self, path, data, send_size, file_size, total_send_size, total_size):
        self._owner.send_feed_file(path, data, send_size, file_size, total_send_size, total_size)

    def send_finish_file(self, path):
        self._owner.send_finish_file(path)

    def send_finish(self):
        self._owner.send_finish()
