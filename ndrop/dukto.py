
import time
import logging
import os.path
import threading
import socket
import socketserver
import ssl
import getpass
import platform

import netifaces

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
    global CHUNK_SIZE
    if size:
        CHUNK_SIZE = size
    else:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sndbuf = s.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        logger.debug('set CHUNK_SIZE: %s' % sndbuf)
        CHUNK_SIZE = sndbuf


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

    def pack_hello(self, tcp_port, dest):
        data = bytearray()
        if tcp_port == DEFAULT_TCP_PORT:
            if dest[0] == '<broadcast>':
                data.append(0x01)
            else:
                data.append(0x02)
        else:
            if dest[0] == '<broadcast>':
                data.append(0x04)
            else:
                data.append(0x05)
            data.extend(tcp_port.to_bytes(2, byteorder='little', signed=True))
        data.extend(get_system_signature())
        return data

    def pack_goodbye(self):
        data = bytearray()
        data.append(0x03)
        data.extend(b'Bye Bye')
        return data

    def unpack_udp(self, agent, client_address, data):
        """
        0x01    <broadcast>, hello
        0x02    <unicast>, hello
        0x03    <broadcast>, bye
        0x04    <broadcast>, hello with port
        0x05    <unicast>, hello with port
        """
        msg_type = data.pop(0)
        if msg_type == 0x03:
            agent.remove_node(client_address[0])
        else:
            if msg_type in [0x04, 0x05]:
                value = data[:2]
                del data[:2]
                tcp_port = int.from_bytes(value, byteorder='little', signed=True)
            else:
                tcp_port = DEFAULT_TCP_PORT
            if data != get_system_signature():  # new machine added
                if msg_type in [0x01, 0x04]:    # <broadcast>
                    agent.say_hello((client_address[0], DEFAULT_UDP_PORT))
                agent.add_node(client_address[0], tcp_port, data.decode('utf-8'))

    def pack_text(self, text):
        data = bytearray()
        text_data = text.encode('utf-8')

        total_size = size = len(text_data)
        record = 1
        data.extend(record.to_bytes(8, byteorder='little', signed=True))
        data.extend(total_size.to_bytes(8, byteorder='little', signed=True))

        data.extend(TEXT_TAG.encode())
        data.append(0x00)
        data.extend(size.to_bytes(8, byteorder='little', signed=True))

        data.extend(text_data)
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
            data.extend(name.encode('utf-8'))
            data.append(0x00)
            data.extend(size.to_bytes(8, byteorder='little', signed=True))
            if size > 0:
                send_size = 0
                with open(path, 'rb') as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE - len(data))
                        if not chunk:
                            break
                        send_size += len(chunk)
                        total_send_size += len(chunk)
                        agent.send_feed_file(
                            name, chunk,
                            send_size, size, total_send_size, total_size,
                        )
                        data.extend(chunk)
                        if len(data) > (CHUNK_SIZE - 1024):
                            yield data
                            data.clear()
            agent.send_finish_file(name)

        if len(data) > 0:
            yield data
            data.clear()

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
    def setup(self):
        self._packet = DuktoPacket()

    def handle(self):
        data = bytearray(self.request[0])
        self._packet.unpack_udp(self.server.agent, self.client_address, data)


class TCPHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self._recv_buff = bytearray()
        self._packet = DuktoPacket()

    def handle(self):
        logger.info('connect from %s:%s' % self.client_address)
        while True:
            data = self.request.recv(CHUNK_SIZE)
            if not data:
                break
            self._recv_buff.extend(data)
            try:
                self._packet.unpack_tcp(self.server.agent, self._recv_buff)
            except Exception as err:
                logger.error('%s - [%s]' % (err, self._recv_buff.hex()))
                break
        self.server.agent.request_finish()

    def finish(self):
        pass


class DuktoServer(Transport):
    _cert = None
    _key = None
    _owner = None
    _tcp_server = None
    _udp_server = None
    _ip_addrs = None
    _broadcasts = None
    _tcp_port = DEFAULT_TCP_PORT
    _packet = None
    _data = None
    _nodes = None
    _loop_hello = True

    def __init__(self, owner, addr, ssl_ck=None):
        if ssl_ck:
            self._cert, self._key = ssl_ck
        self._owner = owner
        self._data = bytearray()
        if ':' in addr:
            ip, port = addr.split(':')
            self._tcp_port = int(port)
        else:
            ip = addr

        self._packet = DuktoPacket()

        self._nodes = {}
        self._udp_server = socketserver.UDPServer(('0.0.0.0', DEFAULT_UDP_PORT), UDPHandler)
        self._udp_server.agent = self

        self._tcp_server = socketserver.TCPServer((ip, self._tcp_port), TCPHandler)
        if self._cert and self._key:
            self._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self._ssl_context.load_cert_chain(self._cert, keyfile=self._key)
            self._tcp_server.socket = self._ssl_context.wrap_socket(
                self._tcp_server.socket, server_side=True)
        self._tcp_server.agent = self
        set_chunk_size()

        self._ip_addrs = []
        self._broadcasts = []
        if ip == '0.0.0.0':
            for ifname in netifaces.interfaces():
                if_addr = netifaces.ifaddresses(ifname)
                for addr in if_addr.get(socket.AF_INET, []):
                    ip_addr = addr.get('addr')
                    broadcast = addr.get('broadcast')
                    ip_addr and self._ip_addrs.append(ip_addr)
                    broadcast and broadcast not in self._broadcasts \
                        and self._broadcasts.append(broadcast)
        else:
            for ifname in netifaces.interfaces():
                if_addr = netifaces.ifaddresses(ifname)
                for addr in if_addr.get(socket.AF_INET, []):
                    ip_addr = addr.get('addr')
                    broadcast = addr.get('broadcast')
                    if ip_addr == ip:
                        self._ip_addrs.append(ip_addr)
                        self._broadcasts.append(broadcast)
                        break

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

        logger.info('My Node: %s' % get_system_signature().decode('utf-8'))
        if len(self._ip_addrs) > 1:
            logger.info('listen on %s:%s - [%s]' % (
                self._tcp_server.server_address[0], self._tcp_server.server_address[1],
                ','.join(self._ip_addrs),
            ))
        else:
            logger.info('listen on %s:%s' % (
                self._tcp_server.server_address[0], self._tcp_server.server_address[1]
            ))
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

    def send_broadcast(self, data, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            for broadcast in self._broadcasts:
                sock.sendto(data, (broadcast, port))
        except Exception as err:
            logger.error('send to "%s" error: %s' % (broadcast, err))
        sock.close()

    def say_hello(self, dest):
        data = self._packet.pack_hello(self._tcp_port, dest)
        if dest[0] == '<broadcast>':
            self.send_broadcast(data, DEFAULT_UDP_PORT)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.sendto(data, dest)
            except Exception as err:
                logger.error('send to "%s" error: %s' % (dest, err))
            sock.close()

    def loop_say_hello(self):
        while self._loop_hello:
            self.say_hello(('<broadcast>', DEFAULT_UDP_PORT))
            time.sleep(30)

    def say_goodbye(self):
        data = self._packet.pack_goodbye()
        self.send_broadcast(data, DEFAULT_UDP_PORT)

    def add_node(self, ip, port, signature):
        if ip not in self._nodes:
            logger.info('Online : [Dukto] %s:%s - %s' % (ip, port, signature))
            self._nodes[ip] = {
                'port': port,
                'signature': signature,
            }

    def remove_node(self, ip):
        if ip in self._nodes:
            logger.info('Offline: [Dukto] %s:%s - %s' % (
                ip, self._nodes[ip]['port'], self._nodes[ip]['signature']))
            del self._nodes[ip]


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
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            sock = ssl_context.wrap_socket(sock, server_side=False)
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
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            sock = ssl_context.wrap_socket(sock, server_side=False)
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
