
import cmd


class NDropShell(cmd.Cmd):
    intro = 'Welcome to the NDrop shell.'
    prompt = '(ndrop)'

    def close(self):
        pass

    def precmd(self, line):
        line = line.lower().strip()
        return line

    def do_bye(self, args):
        'Close ndrop shell and exit.'
        print('Thank you for using NDrop')
        self.close()
        return True
