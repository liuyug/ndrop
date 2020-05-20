
import os
import cmd

from .about import version
from .netdrop import NetDropServer, NetDropClient


class NetDropShell(cmd.Cmd):
    intro = f'Welcome to Ndrop shell v{version}. Type help or ? to list commands.'
    prompt = '(ndrop)$ '
    _mode = None
    _server = None

    def close(self):
        'Close server'
        for transport in self._server._transport:
            transport.request_finish()
            transport.quit_request()
        self._server = None

    def precmd(self, line):
        line = line.lower()
        return line

    def preloop(self):
        pass

    def do_quit(self, arg):
        'Close ndrop shell and exit.'
        print('Thank you for using Ndrop')
        self.close()
        return True

    def do_q(self, arg):
        'Alias for quit.'
        return self.do_quit(arg)

    def do_mode(self, arg):
        'Set client mode: "dukto" or "nitroshare"'
        if arg and arg in ['dukto', 'nitroshare']:
            self._mode = arg
        print(f'Mode: {self._mode}')

    def do_node(self, arg):
        'List online nodes.'
        nodes = self._server.get_nodes()
        if not nodes:
            print('[]')
            return
        for node in nodes:
            print('%(name)s on %(ip)s[%(os)s] with %(mode)s' % node)

    def do_text(self, arg):
        'Send TEXT: text <ip> <text>'
        ip, _, text = arg.partition(' ')
        text = text or 'ndrop test...'
        mode = self._mode or 'dukto'
        client = NetDropClient(ip, mode=mode)
        client.send_text(text)

    def do_file(self, arg):
        'Send FILE: send <ip> <file name>'
        ip, _, fname = arg.partition(' ')
        if not os.path.exists(fname):
            print(f'Could not find file "{fname}"')
            return
        fnames = [fname]
        mode = self._mode or 'dukto'
        client = NetDropClient(ip, mode=mode)
        client.send_files(fnames)

    def do_ls(self, arg):
        'List files in local directory.'
        with os.scandir() as it:
            for entry in sorted(it, key=lambda x: (x.is_file(), x.name)):
                name = entry.name + '/' if entry.is_dir() else entry.name
                print(name)

    def do_pwd(self, arg):
        'Echo local current directory.'
        print(os.getcwd())

    def do_cd(self, arg):
        'change local directory.'
        if arg and os.path.exists(arg):
            os.chdir(arg)
            self._server.saved_to(arg)
