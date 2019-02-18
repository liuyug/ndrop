
import time
import logging
import os.path
import threading
import socket
import socketserver
import ssl
import getpass
import platform

from .transport import Transport


logger = logging.getLogger(__name__)


CHUNK_SIZE = 1024 * 32
DEFAULT_UDP_PORT = 4644
DEFAULT_TCP_PORT = 4644
TEXT_TAG = '___DUKTO___TEXT___'

STATUS = {
    'idle': 0,
    'filename': 1,
    'filesize': 2,
    'data': 3,
}


def set_chunk_size(size=None):
    if size:
        CHUNK_SIZE = size
    else:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sndbuf = s.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        logger.debug('set CHUNK_SIZE: %s' % sndbuf)
        CHUNK_SIZE = sndbuf


def get_network_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.connect(('<broadcast>', 0))
    return s.getsockname()[0]


def get_system_signature():
    user = getpass.getuser()
    uname = platform.uname()
    signature = '%s at %s (%s)' % (user, uname.node, uname.system)
    return signature.encode('utf-8')


class DuktoPacket():
    _status = STATUS['idle']
    _record = 0
    _recv_record = 0
    _total_size = 0
    _total_recv_size = 0
    _filename = None
    _filesize = 0
    _recv_file_size = 0

    def pack_hello(self, dest, my_port):
        data = bytearray()
        if my_port == DEFAULT_UDP_PORT:
            if dest[0] == '<broadcast>':
                data.append(0x01)
            else:
                data.append(0x02)
        else:
            if dest[0] == '<broadcast>':
                data.append(0x04)
            else:
                data.append(0x05)
            data.extend(my_port.to_bytes(2, byteorder='little', signed=True))
        data.extend(get_system_signature())
        return data

    def pack_goodbye(self):
        data = bytearray()
        data.append(0x03)
        data.extend(b'Bye Bye')
        return data

    def unpack_udp(self, agent, client_address, data):
        msg_type = data.pop(0)
        if msg_type in [0x01, 0x02, 0x04, 0x05]:
            if msg_type in [0x04, 0x05]:
                value = data[:2]
                del data[:2]
                port = int.from_bytes(value, byteorder='little', signed=True)
            else:
                port = DEFAULT_UDP_PORT
            if data != get_system_signature():  # new machine added
                if msg_type == 0x01:
                    # unicast
                    agent.say_hello((client_address[0], port))
                agent.add_machine(
                    '%s:%s' % (client_address[0], port), data.decode('utf-8'))
        elif msg_type == 0x03:
            agent.remove_machine('%s:%s' % client_address)

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

    def unpack_tcp(self, agent, data):
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
                    agent.recv_feed_file(
                        self._filename, None,
                        self._recv_file_size, self._filesize,
                        self._total_recv_size, self._total_size,
                    )
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


class UDPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data = bytearray(self.request[0])
        self.server.agent._packet.unpack_udp(
            self.server.agent, self.client_address, data)


class TCPHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self._recv_buff = bytearray()

    def handle(self):
        logger.info('connect from %s:%s' % self.client_address)
        while True:
            data = self.request.recv(CHUNK_SIZE)
            if not data:
                break
            self._recv_buff.extend(data)
            self.server.agent._packet.unpack_tcp(
                self.server.agent, self._recv_buff)
        self.server.agent.request_finish()

    def finish(self):
        pass


class DuktoServer(Transport):
    _cert = None
    _key = None
    _owner = None
    _tcp_server = None
    _udp_server = None
    _tcp_port = DEFAULT_TCP_PORT
    _udp_port = DEFAULT_UDP_PORT
    _packet = None
    _data = None
    _machines = None
    _loop_hello = True

    def __init__(self, owner, addr, ssl_ck=None):
        if ssl_ck:
            self._cert, self._key = ssl_ck
        self._owner = owner
        self._data = bytearray()
        if ':' in addr:
            ip, port = addr.split(':')
            self._tcp_port = self._udp_port = int(port)
        else:
            ip = addr

        self._packet = DuktoPacket()

        self._machines = {}
        self._udp_server = socketserver.UDPServer(('', self._udp_port), UDPHandler)
        self._udp_server.agent = self

        self._tcp_server = socketserver.TCPServer((ip, self._tcp_port), TCPHandler)
        if False and self._cert and self._key:
            self._tcp_server.socket = ssl.wrap_socket(
                self._tcp_server.socket,
                keyfile=self._key, certfile=self._cert, server_side=True)
        self._tcp_server.agent = self
        set_chunk_size()

    def wait_for_request(self):
        threading.Thread(
            name='Online',
            target=self._udp_server.serve_forever,
            daemon=True,
        ).start()
        threading.Thread(
            name='Hello',
            target=self.loop_say_hello,
            daemon=True,
        ).start()

        logger.info('My Signature: %s' % get_system_signature().decode('utf-8'))
        addr = get_network_ip()
        logger.info('listen on %s:%s' % (addr, self._tcp_server.server_address[1]))
        try:
            self._tcp_server.serve_forever()
        except KeyboardInterrupt:
            raise
        finally:
            logger.info('\nwait to quit...')
            self._loop_hello = False
            self.say_goodbye()
            self._tcp_server.shutdown()
            self._udp_server.shutdown()

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

    def say_hello(self, dest):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        data = self._packet.pack_hello(dest, self._udp_port)
        sock.sendto(data, dest)
        sock.close()

    def loop_say_hello(self):
        while self._loop_hello:
            self.say_hello(('<broadcast>', DEFAULT_UDP_PORT))
            time.sleep(10)

    def say_goodbye(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        data = self._packet.pack_goodbye()
        sock.sendto(data, ('<broadcast>', DEFAULT_UDP_PORT))
        for addr in self._machines:
            ip, port = addr.split(':')
            port = int(port)
            if port != DEFAULT_UDP_PORT:
                sock.sendto(data, (ip, port))
        sock.close()

    def add_machine(self, addr, name):
        if addr not in self._machines:
            logger.info('Online : %s - %s' % (addr, name))
            self._machines[addr] = name

    def remove_machine(self, addr):
        name = self._machines.get(addr)
        if name:
            logger.info('Offline: %s - %s' % (addr, name))
            del self._machines[addr]


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
        set_chunk_size()

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
