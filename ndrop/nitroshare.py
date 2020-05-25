
import datetime
import time
import logging
import os.path
import threading
import socket
import socketserver
import struct
import ssl
import platform
import uuid
import json

from .transport import Transport, get_broadcast_address
from .about import get_system_symbol


logger = logging.getLogger(__name__)


CHUNK_SIZE = 1024 * 64
DEFAULT_UDP_PORT = 40816
DEFAULT_TCP_PORT = 40818

STATUS = {
    'idle': 0,
    'header': 1,
    'data': 2,
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


def create_signature(node):
    signature = '%(name)s (%(operating_system)s)' % (node)
    return signature


def parse_signature(signature):
    s = signature.split(' ')
    s[-1] = s[-1].strip('()')
    return s


def format_signature(signature):
    s = parse_signature(signature)
    return '@%s(%s)' % (s[0], get_system_symbol(s[1]))


class Packet():
    _status = STATUS['idle']
    _record = 0
    _recv_record = 0
    _total_size = 0
    _total_recv_size = 0
    _filename = None
    _filesize = 0
    _recv_file_size = 0

    def pack_hello(self, node, dest):
        return json.dumps(node).encode('utf-8')

    def unpack_udp(self, agent, client_address, data):
        node = json.loads(data.decode('utf-8'))
        if node['uuid'] != agent._node['uuid']:  # no me
            if client_address[0] in agent._nodes:
                agent.update_node(client_address[0], node)
            else:
                agent.say_hello((client_address[0], agent._udp_port))
                agent.add_node(client_address[0], node)

    def pack_success(self):
        data = bytearray()
        data.extend(int(1).to_bytes(4, byteorder='little', signed=True))
        data.append(0x00)
        return data

    def pack_error(self, message):
        buff = message.encode('utf-8')
        data = bytearray()
        data.extend((len(buff) + 1).to_bytes(4, byteorder='little', signed=True))
        data.append(0x01)
        data.extend(buff)
        return data

    def pack_files_header(self, name, total_size, count):
        """transfer header"""
        jdata = {}
        jdata['name'] = name
        jdata['size'] = '%s' % total_size
        jdata['count'] = '%s' % count
        bdata = json.dumps(jdata).encode('utf-8')

        data = bytearray()
        data.extend((len(bdata) + 1).to_bytes(4, byteorder='little', signed=True))
        data.append(0x02)
        data.extend(bdata)
        return data

    def pack_files(self, agent, total_size, files):
        data = bytearray()
        total_send_size = 0
        for path, name, size in files:
            # file header
            jdata = {}
            jdata['name'] = name
            if size == -1:
                jdata['directory'] = True
            else:
                jdata['directory'] = False
                jdata['size'] = '%s' % size
            jdata['created'] = ''
            jdata['last_modified'] = ''
            jdata['last_read'] = ''
            bdata = json.dumps(jdata).encode('utf-8')

            data.extend((len(bdata) + 1).to_bytes(4, byteorder='little', signed=True))
            data.append(0x02)
            data.extend(bdata)
            send_size = 0

            if size < 0:    # directory
                agent.send_feed_file(
                    name, None,
                    send_size, -1, total_send_size, total_size,
                )
            elif size == 0:
                agent.send_feed_file(
                    name, b'',
                    send_size, 0, total_send_size, total_size,
                )
            else:
                with open(path, 'rb') as f:
                    while True:
                        packet_size = min(CHUNK_SIZE - len(data), size - send_size)
                        chunk = f.read(packet_size)
                        if not chunk:
                            break
                        # binary header, every binary packet is less than CHUNK_SIZE
                        data.extend((packet_size + 1).to_bytes(4, byteorder='little', signed=True))
                        data.append(0x03)
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
            if self._status == STATUS['idle']:  # transfer header
                size, typ = struct.unpack('<lb', data[:5])
                size -= 1
                if size > len(data):
                    return
                del data[:5]
                if size == 0 and typ == 0x00:
                    return
                elif size > 0 and typ == 0x01:
                    message = data[:size].decode('utf-8')
                    del data[:size]
                    logger.info('Error: %s' % message)
                    return
                elif typ == 0x02:   # json, transfer header
                    jdata = json.loads(data[:size])
                    del data[:size]
                    if 'count' not in jdata:
                        raise ValueError('Error: %s' % jdata)
                    self._total_size = int(jdata['size'])
                    self._record = int(jdata['count'])
                    self._status = STATUS['header']
            elif self._status == STATUS['header']:  # json, file header
                size, typ = struct.unpack('<lb', data[:5])
                size -= 1
                if size > len(data):
                    return
                del data[:5]
                if typ == 0x02:   # json
                    jdata = json.loads(data[:size])
                    del data[:size]
                    if 'directory' not in jdata:  # file header
                        raise ValueError('Error: %s' % jdata)
                    self._recv_file_size = 0
                    self._filename = jdata['name']
                    if jdata['directory']:  # directory
                        self._filesize = -1
                    else:
                        self._filesize = int(jdata['size'])

                    if self._filesize > 0:
                        self._status = STATUS['data']
                    else:
                        if self._filesize < 0:
                            chunk = None
                        else:
                            chunk = b''
                        self._recv_record += 1
                        agent.recv_feed_file(
                            self._filename, chunk,
                            self._recv_file_size, self._filesize,
                            self._total_recv_size, self._total_size,
                        )
                        agent.recv_finish_file(self._filename)
                        if self._record == self._recv_record and  \
                                self._total_recv_size == self._total_size:
                            self._status = STATUS['idle']
                            return True
                        else:
                            self._status = STATUS['header']
                else:
                    raise ValueError('Error Type: %s' % typ)
            elif self._status == STATUS['data']:
                size, typ = struct.unpack('<lb', data[:5])
                size -= 1
                if size > len(data):    # many packets for one file.
                    return
                del data[:5]
                if typ == 0x03:   # data
                    self._recv_file_size += size
                    self._total_recv_size += size
                    agent.recv_feed_file(
                        self._filename, data[:size],
                        self._recv_file_size, self._filesize,
                        self._total_recv_size, self._total_size,
                    )
                    del data[:size]
                    if self._recv_file_size == self._filesize:
                        self._status = STATUS['header']
                        self._recv_record += 1
                        agent.recv_finish_file(self._filename)
                    if self._record == self._recv_record and  \
                            self._total_recv_size == self._total_size:
                        self._status = STATUS['idle']
                        return True


class UDPHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self._packet = Packet()

    def handle(self):
        if self.client_address[0] not in self.server.agent._ip_addrs:
            data = bytearray(self.request[0])
            self._packet.unpack_udp(self.server.agent, self.client_address, data)


class TCPHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self._recv_buff = bytearray()
        self._packet = Packet()

    def handle(self):
        logger.info('[NitroShare] connect from %s:%s' % self.client_address)
        while True:
            data = self.request.recv(CHUNK_SIZE)
            if not data:
                break
            self._recv_buff.extend(data)
            try:
                ret = self._packet.unpack_tcp(self.server.agent, self._recv_buff)
            except Exception as err:
                logger.error('%s' % err)
                break
            if ret:
                data = self._packet.pack_success()
                self.request.sendall(data)
                break
        self.server.agent.request_finish()

    def finish(self):
        pass


class NitroshareServer(Transport):
    _name = 'NitroShare'
    _cert = None
    _key = None
    _owner = None
    _tcp_server = None
    _udp_server = None
    _tcp_port = DEFAULT_TCP_PORT
    _udp_port = DEFAULT_UDP_PORT
    _ip_addrs = None
    _broadcasts = None
    _packet = None
    _data = None
    _nodes = None
    _loop_hello = True
    _hello_interval = 5

    def __init__(self, owner, addr, ssl_ck=None):
        if ssl_ck:
            self._cert, self._key = ssl_ck
        self._owner = owner
        self._data = bytearray()
        addr = addr.split(':')
        ip = addr.pop(0)
        if len(addr) > 0:
            self._tcp_port = int(addr.pop(0))
        if len(addr) > 0:
            self._udp_port = int(addr.pop(0))

        self._packet = Packet()
        uname = platform.uname()
        data = {}
        data['uuid'] = '%s' % uuid.uuid1()
        data['name'] = uname.node
        data['operating_system'] = uname.system.lower()
        data['port'] = '%s' % self._tcp_port
        data['uses_tls'] = bool(self._cert) and bool(self._key)
        self._node = data

        self._nodes = {}
        self._udp_server = socketserver.UDPServer((ip, self._udp_port), UDPHandler)
        self._udp_server.agent = self

        self._tcp_server = socketserver.TCPServer((ip, self._tcp_port), TCPHandler)
        if self._cert and self._key:
            self._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            self._ssl_context.load_cert_chain(self._cert, keyfile=self._key)
            self._tcp_server.socket = self._ssl_context.wrap_socket(
                self._tcp_server.socket, server_side=True)
        self._tcp_server.agent = self
        set_chunk_size()

        self._ip_addrs, self._broadcasts = get_broadcast_address(ip)

    def wait_for_request(self):
        threading.Thread(
            name='nitroshare server',
            target=self._udp_server.serve_forever,
            daemon=True,
        ).start()
        threading.Thread(
            name='nitroshare hello',
            target=self.loop_say_hello,
            daemon=True,
        ).start()

        if len(self._ip_addrs) > 1:
            logger.info('[NitroShare] listen on %s:%s(tcp):%s(udp) - bind on %s' % (
                self._tcp_server.server_address[0], self._tcp_server.server_address[1],
                self._udp_server.server_address[1],
                ', '.join(self._ip_addrs),
            ))
        else:
            logger.info('[NitroShare] listen on %s:%s(tcp):%s(udp)' % (
                self._tcp_server.server_address[0], self._tcp_server.server_address[1],
                self._udp_server.server_address[1],
            ))

    def handle_request(self):
        self._tcp_server.handle_request()

    def quit_request(self):
        self._loop_hello = False
        self._udp_server.shutdown()

    def fileno(self):
        return self._tcp_server.fileno()

    def recv_feed_file(self, path, data, recv_size, file_size, total_recv_size, total_size):
        self._owner.recv_feed_file(
            path, data, recv_size, file_size, total_recv_size, total_size)

    def recv_finish_file(self, path):
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
            if err.errno != 101:
                logger.error('[NitroShare]send to "%s" error: %s' % (broadcast, err))
        sock.close()

    def say_hello(self, dest):
        data = self._packet.pack_hello(self._node, dest)
        if dest[0] == '<broadcast>':
            self.send_broadcast(data, dest[1])
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.sendto(data, dest)
            except Exception as err:
                logger.error('[NitroShare]send to "%s" error: %s' % (dest, err))
            sock.close()

    def loop_say_hello(self):
        while self._loop_hello:
            self.say_hello(('<broadcast>', self._udp_port))
            self.check_node()
            time.sleep(self._hello_interval)

    def add_node(self, ip, node):
        if ip not in self._nodes:
            signature = create_signature(node)
            logger.info('Online : [NitroShare] %s:%s - %s' % (
                ip, node['port'], format_signature(signature)))
            self._nodes[ip] = node
            self._nodes[ip]['last_ping'] = datetime.datetime.now()

    def update_node(self, ip, node):
        now = datetime.datetime.now()
        self._nodes[ip] = node
        self._nodes[ip]['last_ping'] = now

    def check_node(self):
        now = datetime.datetime.now()
        timeout_nodes = []
        for ip, node in self._nodes.items():
            if (now - datetime.timedelta(seconds=(self._hello_interval + 5))) > node['last_ping']:
                timeout_nodes.append(ip)
        for ip in timeout_nodes:
            self.remove_node(ip)

    def remove_node(self, ip):
        if ip in self._nodes:
            node = self._nodes[ip]
            signature = create_signature(node)
            logger.info('Offline: [NitroShare] %s:%s - %s' % (
                ip, node['port'], format_signature(signature)))
            del self._nodes[ip]


class NitroshareClient(Transport):
    _cert = None
    _key = None
    _owner = None
    _packet = None

    def __init__(self, owner, addr, ssl_ck=None):
        if ssl_ck:
            self._cert, self._key = ssl_ck
        self._owner = owner
        addr = addr.split(':')
        ip = addr.pop(0)
        if len(addr) > 0:
            tcp_port = int(addr.pop(0))
        else:
            tcp_port = DEFAULT_TCP_PORT
        self._address = (ip, tcp_port)
        self._packet = Packet()
        set_chunk_size()

    def send_files(self, total_size, files):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self._cert and self._key:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            sock = ssl_context.wrap_socket(sock, server_side=False)
        sock.connect(self._address)

        uname = platform.uname()
        try:
            header = self._packet.pack_files_header(uname.node, total_size, len(files))
            sock.sendall(header)

            for chunk in self._packet.pack_files(self, total_size, files):
                sock.sendall(chunk)
            # receive feedback message
            data = bytearray()
            while True:
                chunk = sock.recv(CHUNK_SIZE)
                if not chunk:
                    break
                data.extend(chunk)
            self._packet.unpack_tcp(self, data)
        except KeyboardInterrupt:
            pass
        except Exception:
            raise
        sock.close()
        self.send_finish()

    def send_feed_file(self, path, data, send_size, file_size, total_send_size, total_size):
        self._owner.send_feed_file(path, data, send_size, file_size, total_send_size, total_size)

    def send_finish_file(self, path):
        self._owner.send_finish_file(path)

    def send_finish(self):
        self._owner.send_finish()
