import sys
import time
import logging
import os.path
import threading
import socket
import socketserver
import ssl
import getpass
import platform

from .transport import Transport, get_broadcast_address, CHUNK_SIZE, set_chunk_size
from .about import get_system_symbol


logger = logging.getLogger(__name__)


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
    _name = 'Dukto'
    _status = STATUS['idle']
    _record = 0
    _recv_record = 0
    _total_size = 0
    _total_recv_size = 0
    _filename = None
    _filesize = 0
    _recv_file_size = 0

    def pack_hello(self, node, tcp_port, dest):
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
        data.extend(node.encode('utf-8'))
        return data

    def pack_goodbye(self):
        data = bytearray()
        data.append(0x03)
        data.extend(b'Bye Bye')
        return data

    def unpack_udp(self, agent, data, client_address):
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
            if data != agent.get_signature().encode('utf-8'):  # no me
                if msg_type in [0x01, 0x04]:    # <broadcast>
                    agent.say_hello((client_address[0], agent._udp_port))
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
        transfer_abort = False
        for path, name, size in files:
            # packet format
            # B * n B    D    B * size
            # name  0x00 size data
            data.extend(name.encode('utf-8'))
            data.append(0x00)
            data.extend(size.to_bytes(8, byteorder='little', signed=True))
            send_size = 0
            if size < 0:  # directory
                agent.send_feed_file(
                    name, None,
                    send_size, -1, total_send_size, total_size)
            elif size == 0:  # file, size equal 0
                agent.send_feed_file(
                    name, b'',
                    send_size, 0, total_send_size, total_size)
            else:
                file_changed = False
                with open(path, 'rb') as f:
                    while not file_changed:
                        chunk = f.read(CHUNK_SIZE - len(data))

                        # next file
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
                            if cont.lower() != 'yes':
                                transfer_abort = True
                        send_size += len(chunk)
                        total_send_size += len(chunk)
                        agent.send_feed_file(
                            name, chunk,
                            send_size, size, total_send_size, total_size,
                        )
                        data.extend(chunk)
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

                if self._filesize > 0:
                    self._status = STATUS['data']
                else:
                    if self._filesize < 0:    # directory
                        chunk = None
                    else:
                        chunk = b''
                    agent.recv_feed_file(
                        self._filename, chunk,
                        self._recv_file_size, self._filesize,
                        self._total_recv_size, self._total_size,
                        from_addr,
                    )
                    agent.recv_finish_file(self._filename, from_addr)
                    self._recv_record += 1
                    if self._recv_record == self._record and  \
                            self._total_recv_size == self._total_size:
                        self._status = STATUS['idle']
                        data.clear()
                    else:
                        self._status = STATUS['filename']
            elif self._status == STATUS['data']:
                size = min(self._filesize - self._recv_file_size, len(data))
                self._recv_file_size += size
                self._total_recv_size += size

                agent.recv_feed_file(
                    self._filename, data[:size],
                    self._recv_file_size, self._filesize,
                    self._total_recv_size, self._total_size,
                    from_addr,
                )
                del data[:size]

                if self._recv_file_size == self._filesize:
                    self._status = STATUS['filename']
                    self._recv_record += 1
                    agent.recv_finish_file(self._filename, from_addr)
                if self._recv_record == self._record and  \
                        self._total_recv_size == self._total_size:
                    # transfer complete
                    self._status = STATUS['idle']
                    data.clear()
                    return True


class UDPHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self._packet = DuktoPacket()

    def handle(self):
        if self.client_address[0] not in self.server.agent._ip_addrs:
            data = bytearray(self.request[0])
            self._packet.unpack_udp(self.server.agent, data, self.client_address)


class TCPHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self._recv_buff = bytearray()
        self._packet = DuktoPacket()
        self.request.settimeout(20)

    def handle(self):
        logger.info('[Dukto] connect from %s:%s' % self.client_address)
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
                err = 'done'
                break
        if err == 'abort':
            self.server.agent.recv_finish_file(self._packet._filename, self.client_address)
        self.server.agent.recv_finish(self.client_address, err)

    def finish(self):
        pass


class DuktoServer(Transport):
    _name = 'Dukto'
    _cert = None
    _key = None
    _upper_level = None
    _tcp_server = None
    _udp_server = None
    _broadcast_sock = None
    _unicast_sock = None
    _ip_addrs = None
    _broadcasts = None
    _tcp_port = DEFAULT_TCP_PORT
    _udp_port = DEFAULT_UDP_PORT
    _packet = None
    _data = None
    _node = None
    _nodes = None
    _loop_hello = True

    def __init__(self, upper_level, addr, ssl_ck=None):
        if ssl_ck:
            self._cert, self._key = ssl_ck
        addr = addr.split(':')
        ip = addr.pop(0)
        if len(addr) > 0:
            self._tcp_port = int(addr.pop(0))
        if len(addr) > 0:
            self._udp_port = int(addr.pop(0))

        self._node = self.create_node()
        self._upper_level = upper_level
        self._data = bytearray()

        self._packet = DuktoPacket()

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
            name='dukto server',
            target=self._udp_server.serve_forever,
            daemon=True,
        ).start()
        threading.Thread(
            name='dukto hello',
            target=self.loop_say_hello,
            daemon=True,
        ).start()

        logger.info('My Node: %s' % self.format_node())
        if self._tcp_server.server_address[0] == '0.0.0.0':
            logger.info('[Dukto] listen on %s:%s(tcp):%s(udp) - bind on %s' % (
                self._tcp_server.server_address[0], self._tcp_server.server_address[1],
                self._udp_server.server_address[1],
                ', '.join(self._ip_addrs),
            ))
        else:
            logger.info('[Dukto] listen on %s:%s(tcp):%s(udp)' % (
                self._tcp_server.server_address[0], self._tcp_server.server_address[1],
                self._udp_server.server_address[1],
            ))

    def handle_request(self):
        self._tcp_server.handle_request()

    def quit_request(self):
        self._loop_hello = False
        self.say_goodbye()
        self._udp_server.shutdown()

    def fileno(self):
        return self._tcp_server.fileno()

    def recv_feed_file(self,
                       path, data,
                       recv_size, file_size,
                       total_recv_size, total_size,
                       from_addr):
        if path == TEXT_TAG:
            self._upper_level.recv_feed_text(data, from_addr)
        else:
            self._upper_level.recv_feed_file(
                path, data,
                recv_size, file_size,
                total_recv_size, total_size, from_addr)

    def recv_finish_file(self, path, from_addr):
        if path == TEXT_TAG:
            self._upper_level.recv_finish_text(from_addr)
        else:
            self._upper_level.recv_finish_file(path, from_addr)

    def recv_finish(self, from_addr, err):
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
                logger.error('[Dukto] send broadcast to "%s:%s": %s' % (broadcast, port, err))

    def say_hello(self, dest):
        data = self._packet.pack_hello(
            self.get_signature(), self._tcp_port, dest)
        if dest[0] == '<broadcast>':
            self.send_broadcast(data, dest[1])
        else:
            try:
                self._unicast_sock.sendto(data, dest)
            except Exception as err:
                logger.error('[Dukto] send to "%s" error: %s' % (dest, err))

    def loop_say_hello(self):
        while self._loop_hello:
            self.say_hello(('<broadcast>', self._udp_port))
            time.sleep(30)

    def say_goodbye(self):
        data = self._packet.pack_goodbye()
        self.send_broadcast(data, self._udp_port)

    def add_node(self, ip, port, signature):
        if ip not in self._nodes:
            info = signature.split(' ')
            self._nodes[ip] = {
                'ip': ip,
                'port': port,
                'user': info[0],
                'name': info[2],
                'operating_system': info[3].strip('()').lower(),
                'mode': self._name,
                'type': 'guest',
            }
            self._nodes[ip]['long_name'] = self.format_node(self._nodes[ip])
            self._upper_level.add_node(self._nodes[ip])

    def remove_node(self, ip):
        if ip in self._nodes:
            self._upper_level.remove_node(self._nodes[ip])
            del self._nodes[ip]

    def get_signature(self, node=None):
        node = node or self._node
        signature = '%(user)s at %(name)s (%(operating_system)s)' % node
        return signature

    def create_node(self):
        user = getpass.getuser()
        uname = platform.uname()
        node = {
            'port': self._tcp_port,
            'user': user,
            'name': uname.node,
            'operating_system': uname.system,
        }
        return node

    def format_node(self, node=None):
        node = node or self._node
        return '%s@%s(%s)' % (
            node['user'], node['name'],
            get_system_symbol(node['operating_system'])
        )


class DuktoClient(Transport):
    _cert = None
    _key = None
    _upper_level = None
    _packet = None
    _address = None
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
        self._packet = DuktoPacket()
        set_chunk_size()

    def send_text(self, text):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self._cert and self._key:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            sock = ssl_context.wrap_socket(sock, server_side=False)
        data = self._packet.pack_text(text)
        sock.settimeout(self._timeout)
        err = 'done'
        try:
            sock.connect(self._address)
            sock.sendall(data)
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

    def send_files(self, total_size, files):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self._cert and self._key:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            sock = ssl_context.wrap_socket(sock, server_side=False)
        header = self._packet.pack_files_header(len(files), total_size)
        sock.settimeout(self._timeout)
        err = 'done'
        try:
            sock.connect(self._address)
            sock.sendall(header)
            for chunk in self._packet.pack_files(self, total_size, files):
                sock.sendall(chunk)
        except KeyboardInterrupt:
            pass
        except socket.timeout as e:
            err = e
            logger.error(err)
        except Exception as e:
            err = e
            logger.error(err)
            raise
        sock.close()
        self.send_finish(err)

    def send_feed_file(self, path, data, send_size, file_size, total_send_size, total_size):
        self._upper_level.send_feed_file(path, data, send_size, file_size, total_send_size, total_size)

    def send_finish_file(self, path):
        self._upper_level.send_finish_file(path)

    def send_finish(self, err):
        self._upper_level.send_finish(err)
