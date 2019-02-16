
import logging


logger = logging.getLogger(__name__)


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
