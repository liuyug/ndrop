
import logging
import socket
import ipaddress
import math
import platform
from os import environ

import ifaddr

logger = logging.getLogger(__name__)


CHUNK_SIZE = 1024 * 64


def set_chunk_size(size=None):
    global CHUNK_SIZE

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sndbuf = s.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
    CHUNK_SIZE = min(sndbuf, CHUNK_SIZE)

    if size:
        CHUNK_SIZE = min(size, sndbuf)
    logger.debug('CHUNK_SIZE: %s' % CHUNK_SIZE)


def human_size(size):
    if size == 0:
        return "0 B"
    unit = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size, 1024)))
    p = math.pow(1024, i)
    s = round(size / p, 2)
    return "%s %s" % (s, unit[i])


def get_broadcast_address(ip_addr=None):
    ip_addrs = []
    broadcasts = []
    for adapter in ifaddr.get_adapters():
        for a_ip in adapter.ips:
            if a_ip.is_IPv4:
                ip = ipaddress.ip_address(a_ip.ip)
                if ip.is_loopback or ip.is_link_local:
                    continue
                mask = 0xffffffff << (32 - a_ip.network_prefix)
                net_addr_int = int.from_bytes(ip.packed, 'big') & mask
                net_ip = ipaddress.ip_network((net_addr_int, a_ip.network_prefix))

                ip_addrs.append(str(ip))
                broadcasts.append(str(net_ip.broadcast_address))
    if ip_addr and ip_addr != '0.0.0.0':
        if ip_addr in ip_addrs:
            idx = ip_addrs.index(ip_addr)
            return [ip_addr], [broadcasts[idx]]
        else:
            return [], []

    return ip_addrs, broadcasts


def get_platform_system():
    system = platform.system().lower()
    if 'ANDROID_ARGUMENT' in environ:
        return 'android'
    elif system in ('win32', 'cygwin'):
        return 'windows'
    elif system == 'darwin':
        return 'macosx'
    elif system.startswith('linux'):
        return 'linux'
    elif system.startswith('freebsd'):
        return 'linux'
    return system


def get_platform_name():
    node = platform.node()
    return node


class Transport(object):
    _timeout = 5

    def send_text(self, text):
        pass

    def send_files(self, total_size, files):
        pass

    def send_feed_file(self, path, data, send_size, file_size, total_send_size, total_size):
        pass

    def send_finish_file(self, path):
        pass

    def send_finish(self, err=None):
        pass

    def recv_finish(self, err=None):
        pass

    def recv_feed_file(self, path, data, recv_size, file_size, total_recv_size, total_size, from_addr):
        pass

    def recv_finish_file(self, path, from_addr):
        pass
