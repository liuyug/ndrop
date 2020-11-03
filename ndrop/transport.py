
import logging
import socket
import ipaddress

import ifaddr

logger = logging.getLogger(__name__)


def drop_ip(ip_addr):
    exclude_ipaddr = ['127.0', '169.254']
    for e_ip in exclude_ipaddr:
        if ip_addr.startswith(e_ip):
            return True


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


def get_broadcast_address2(ip_addr=None):
    import netifaces
    ip_addrs = []
    broadcasts = []
    if not ip_addr or ip_addr == '0.0.0.0':
        for ifname in netifaces.interfaces():
            if_addr = netifaces.ifaddresses(ifname)
            for addr in if_addr.get(socket.AF_INET, []):
                ip_addr = addr.get('addr')
                if drop_ip(ip_addr):
                    continue
                broadcast = addr.get('broadcast')
                ip_addr and ip_addrs.append(ip_addr)
                broadcast and broadcast not in broadcasts \
                    and broadcasts.append(broadcast)
    else:
        for ifname in netifaces.interfaces():
            if_addr = netifaces.ifaddresses(ifname)
            for addr in if_addr.get(socket.AF_INET, []):
                if ip_addr == addr.get('addr'):
                    if drop_ip(ip_addr):
                        continue
                    ip_addrs.append(ip_addr)
                    broadcast = addr.get('broadcast')
                    broadcasts.append(broadcast)
                    break
    return ip_addrs, broadcasts


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

    def request_finish(self, err=None):
        pass

    def recv_feed_file(self, path, data, recv_size, file_size, total_recv_size, total_size):
        pass

    def recv_finish_file(self, path):
        pass
