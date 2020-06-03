
import logging
import socket

import netifaces


logger = logging.getLogger(__name__)


def get_broadcast_address(ip_addr=None):
    ip_addrs = []
    broadcasts = []
    exclude_ipaddr = ['127.0', '169.254']
    if not ip_addr or ip_addr == '0.0.0.0':
        for ifname in netifaces.interfaces():
            if_addr = netifaces.ifaddresses(ifname)
            for addr in if_addr.get(socket.AF_INET, []):
                ip_addr = addr.get('addr')
                for e_ip in exclude_ipaddr:
                    if ip_addr.startswith(e_ip):
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
                    for e_ip in exclude_ipaddr:
                        if ip_addr.startswith(e_ip):
                            continue
                    ip_addrs.append(ip_addr)
                    broadcast = addr.get('broadcast')
                    broadcasts.append(broadcast)
                    break
    return ip_addrs, broadcasts


class Transport(object):
    def send_text(self, text):
        pass

    def send_files(self, total_size, files):
        pass

    def send_feed_file(self, path, data, send_size, file_size, total_send_size, total_size):
        pass

    def send_finish_file(self, path):
        pass

    def send_finish(self):
        pass

    def request_finish(self):
        pass

    def recv_feed_file(self, path, data, recv_size, file_size, total_recv_size, total_size):
        pass

    def recv_finish_file(self, path):
        pass
