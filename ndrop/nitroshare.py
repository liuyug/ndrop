import sys
import datetime
import time
import logging
import os.path
import threading
import socket
import socketserver
import struct
import ssl
import uuid
import json

from .transport import Transport, \
    get_broadcast_address, CHUNK_SIZE, set_chunk_size, \
    get_platform_name, get_platform_system
from .about import get_system_symbol


logger = logging.getLogger(__name__)


DEFAULT_UDP_PORT = 40816
DEFAULT_TCP_PORT = 40818

STATUS = {
    'idle': 0,
    'header': 1,
    'data': 2,
}


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
        hello_node = {}
        hello_node['uuid'] = node['uuid']
        hello_node['name'] = node['name']
        hello_node['operating_system'] = node['operating_system']
        hello_node['port'] = node['port']
        hello_node['uses_tls'] = node['uses_tls']
        return json.dumps(node).encode('utf-8')

    def unpack_udp(self, agent, data, client_address):
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
        transfer_abort = False
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

            # packet format
            # L    B   B * (size - 1)
            # size tag data
            data.extend((len(bdata) + 1).to_bytes(4, byteorder='little', signed=True))
            data.append(0x02)
            data.extend(bdata)
            if len(data) >= CHUNK_SIZE:
                yield data[:CHUNK_SIZE]
                del data[:CHUNK_SIZE]

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
                file_changed = False
                with open(path, 'rb') as f:
                    while not file_changed:
                        chunk = f.read(CHUNK_SIZE - len(data))
                        if not chunk:
                            if (len(data) + 128) >= CHUNK_SIZE:
                                yield data[:CHUNK_SIZE]
                                del data[:CHUNK_SIZE]
                            break
                        if (send_size + len(chunk)) > size:
                            file_changed = True
                            # correct size
                            chunk = chunk[:size - send_size]
                            logger.error('File Changed: [%s] %s => %s.' % (name, size, send_size))
                            cont = input('Drop data and continue? [Yes/No]')
                            if cont != 'Yes':
                                transfer_abort = True
                        # binary header, every binary packet is less than CHUNK_SIZE
                        data.extend((len(chunk) + 1).to_bytes(4, byteorder='little', signed=True))
                        data.append(0x03)
                        send_size += len(chunk)
                        total_send_size += len(chunk)
                        agent.send_feed_file(
                            name, chunk,
                            send_size, size, total_send_size, total_size,
                        )
                        data.extend(chunk)
                        # send if packet_size more than chunk_size
                        if len(data) >= CHUNK_SIZE:
                            yield data[:CHUNK_SIZE]
                            del data[:CHUNK_SIZE]
            agent.send_finish_file(name)
            if transfer_abort:
                break
        if len(data) > 0:
            yield data
            data.clear()
        if transfer_abort:
            sys.exit('Transfer Abort!!!')

    def unpack_tcp(self, agent, data, from_addr):
        while len(data) > 0:
            if self._status == STATUS['idle']:  # transfer header
                if len(data) < 5:
                    return
                size, typ = struct.unpack('<lb', data[:5])
                # 4    1   ...
                # size tag data
                # size = sizeof(tag + data)
                if size > (len(data) - 4):
                    return
                del data[:5]
                size -= 1
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
                if len(data) < 5:
                    return
                size, typ = struct.unpack('<lb', data[:5])
                if size > (len(data) - 4):
                    return
                del data[:5]
                size -= 1
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
                            from_addr,
                        )
                        agent.recv_finish_file(self._filename, from_addr)
                        if self._record == self._recv_record and  \
                                self._total_recv_size == self._total_size:
                            self._status = STATUS['idle']
                            return True
                        else:
                            self._status = STATUS['header']
                else:
                    raise ValueError('Error Type: %s' % typ)
            elif self._status == STATUS['data']:
                if len(data) < 5:
                    return
                size, typ = struct.unpack('<lb', data[:5])
                if size > (len(data) - 4):    # wait for more packet data
                    return
                data_size = size - 1
                if typ == 0x03:   # data
                    self._recv_file_size += data_size
                    self._total_recv_size += data_size
                    agent.recv_feed_file(
                        self._filename, data[5:5 + data_size],
                        self._recv_file_size, self._filesize,
                        self._total_recv_size, self._total_size,
                        from_addr,
                    )
                    del data[:5 + data_size]
                    if self._recv_file_size == self._filesize:
                        self._status = STATUS['header']
                        self._recv_record += 1
                        agent.recv_finish_file(self._filename, from_addr)
                    if self._record == self._recv_record and  \
                            self._total_recv_size == self._total_size:
                        self._status = STATUS['idle']
                        return True
                else:
                    raise ValueError('Error Type: %s' % typ)


class UDPHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self._packet = Packet()

    def handle(self):
        if self.client_address[0] not in self.server.agent._ip_addrs:
            data = bytearray(self.request[0])
            self._packet.unpack_udp(self.server.agent, data, self.client_address)


class TCPHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self._recv_buff = bytearray()
        self._packet = Packet()
        self.request.settimeout(20)

    def handle(self):
        logger.info('[NitroShare] connect from %s:%s' % self.client_address)
        err = ''
        ret = None
        while True:
            try:
                data = self.request.recv(CHUNK_SIZE)
                if not data:
                    err = 'abort'
                    break
                self._recv_buff.extend(data)
                ret = self._packet.unpack_tcp(self.server.agent, self._recv_buff, self.client_address)
            except Exception as e:
                err = e
                logger.error('%s' % err)
                break
            if ret:
                data = self._packet.pack_success()
                self.request.sendall(data)
                err = 'done'
                break
        if err == 'abort':
            self.server.agent.recv_finish_file(self._packet._filename, self.client_address)
        self.server.agent.recv_finish(self.client_address, err)

    def finish(self):
        pass


class NitroshareServer(Transport):
    _name = 'NitroShare'
    _cert = None
    _key = None
    _upper_level = None
    _tcp_server = None
    _udp_server = None
    _tcp_port = DEFAULT_TCP_PORT
    _udp_port = DEFAULT_UDP_PORT
    _unicast_sock = None
    _broadcast_sock = None
    _ip_addrs = None
    _broadcasts = None
    _packet = None
    _data = None
    _nodes = None
    _loop_hello = True
    _hello_interval = 2

    def __repr__(self):
        return '<NitroshareServer>'

    def __init__(self, upper_level, addr, ssl_ck=None):
        if ssl_ck:
            self._cert, self._key = ssl_ck
        self._upper_level = upper_level
        self._data = bytearray()
        addr = addr.split(':')
        ip = addr.pop(0)
        if len(addr) > 0:
            self._tcp_port = int(addr.pop(0))
        if len(addr) > 0:
            self._udp_port = int(addr.pop(0))

        self._packet = Packet()
        data = {}
        data['uuid'] = '%s' % uuid.uuid1()
        data['name'] = get_platform_name()
        data['operating_system'] = get_platform_system()
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

        self._unicast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
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

        if self._tcp_server.server_address[0] == '0.0.0.0':
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

    def recv_feed_file(self, path, data,
                       recv_size, file_size, total_recv_size, total_size,
                       from_addr):
        self._upper_level.recv_feed_file(
            path, data,
            recv_size, file_size, total_recv_size, total_size, from_addr)

    def recv_finish_file(self, path, from_addr):
        self._upper_level.recv_finish_file(path, from_addr)

    def recv_finish(self, from_addr, err):
        """当前任务全部完成"""
        self._upper_level.recv_finish(from_addr, err)

    def send_broadcast(self, data, port):
        try:
            for broadcast in self._broadcasts:
                num = self._broadcast_sock.sendto(data, (broadcast, port))
                assert num == len(data), (broadcast, port, num, len(data))
        except (OSError, socket.herror, socket.gaierror, socket.timeout) as err:
            if err.errno == 101 or err.errno == 10051:  # Network is unreachable
                pass
            else:
                logger.error('[NitroShare] send broadcast to "%s:%s" error: %s' % (broadcast, port, err))

    def say_hello(self, dest):
        data = self._packet.pack_hello(self._node, dest)
        if dest[0] == '<broadcast>':
            self.send_broadcast(data, dest[1])
        else:
            try:
                self._unicast_sock.sendto(data, dest)
            except Exception as err:
                logger.error('[NitroShare]send to "%s" error: %s' % (dest, err))

    def loop_say_hello(self):
        while self._loop_hello:
            self.say_hello(('<broadcast>', self._udp_port))
            self.check_node()
            time.sleep(self._hello_interval)

    def add_node(self, ip, node):
        if ip not in self._nodes:
            self._nodes[ip] = {}
            self._nodes[ip].update(node)
            self._nodes[ip]['ip'] = ip
            self._nodes[ip]['last_ping'] = datetime.datetime.now()
            self._nodes[ip]['user'] = self._name
            self._nodes[ip]['mode'] = self._name
            self._nodes[ip]['long_name'] = self.format_node(self._nodes[ip])
            self._nodes[ip]['type'] = 'guest'
            self._upper_level.add_node(self._nodes[ip])

    def update_node(self, ip, node):
        now = datetime.datetime.now()
        assert ip in self._nodes
        self._nodes[ip]['last_ping'] = now

    def check_node(self):
        now = datetime.datetime.now()
        timeout_nodes = []
        timeout = 10
        for ip, node in self._nodes.items():
            last_valid_time = now - datetime.timedelta(seconds=(self._hello_interval + timeout))
            if last_valid_time > node['last_ping']:
                timeout_nodes.append(ip)
        for ip in timeout_nodes:
            self.remove_node(ip)

    def remove_node(self, ip):
        if ip in self._nodes:
            self._upper_level.remove_node(self._nodes[ip])
            del self._nodes[ip]

    def get_signature(self, node=None):
        node = node or self._node
        signature = '%(name)s (%(operating_system)s)' % node
        return signature

    def format_node(self, node=None):
        node = node or self._node
        return '%s@%s(%s)' % (self._name, node['name'], get_system_symbol(node['operating_system']))


class NitroshareClient(Transport):
    _cert = None
    _key = None
    _upper_level = None
    _packet = None
    _timeout = 5

    def __init__(self, upper_level, addr, ssl_ck=None):
        if ssl_ck:
            self._cert, self._key = ssl_ck
        self._upper_level = upper_level
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

        sock.settimeout(self._timeout)
        err = 'done'
        try:
            header = self._packet.pack_files_header(get_platform_name(), total_size, len(files))
            sock.connect(self._address)
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
            self._packet.unpack_tcp(self, data, self._address)
        except KeyboardInterrupt:
            pass
        except socket.timeout as e:
            err = e
            logger.error(err)
        except Exception as e:
            err = e
            logger.error(err)
        sock.close()
        self.send_finish(err)

    def send_feed_file(self, path, data, send_size, file_size, total_send_size, total_size):
        self._upper_level.send_feed_file(path, data, send_size, file_size, total_send_size, total_size)

    def send_finish_file(self, path):
        self._upper_level.send_finish_file(path)

    def send_finish(self, err):
        self._upper_level.send_finish(err)
