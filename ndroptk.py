#!/usr/bin/env python3
# -*- encoding:utf-8 -*-

import os
import sys
import platform
import re
import threading
import queue
import logging

from PIL import Image, ImageTk
import tkinterdnd2 as tkdnd
import tkinter as tk
import tkinter.ttk as ttk


from ndrop import about
from ndrop.netdrop import NetDropServer, NetDropClient

logger = logging.getLogger(__name__)


class GUIProgressBar(ttk.Progressbar):
    def __init__(self, parent, **kwargs):
        self.parent = parent
        super().__init__(parent, **kwargs)

    def update(self, step):
        self.step(step)

    def write(self, message, file=None):
        logger.info(message)

    def close(self):
        self.destroy()
        logger.info('done')
        self.parent.status.set('done')


class GUINetDropServer(NetDropServer):
    progress = None

    def __init__(self, parent, *args):
        self.parent = parent
        super().__init__(*args)

    def init_bar(self, max_value):
        progress = GUIProgressBar(
            self.parent._me, orient=tk.HORIZONTAL,
            maximum=max_value,
            mode='determinate')
        progress.grid(row=1, column=1, sticky='w')
        progress.lift()
        return progress

    def add_node(self, node):
        self.parent.queue.put_nowait(('add_node', node))
        self.parent.event_generate('<<queue_event>>')

    def remove_node(self, node):
        self.parent.queue.put_nowait(('remove_node', node))
        self.parent.event_generate('<<queue_event>>')


class GUINetDropClient(NetDropClient):
    def __init__(self, parent):
        self.parent = parent
        cert = None
        key = None
        super().__init__(parent._node['ip'], parent._node['mode'], ssl_ck=(cert, key))

    def init_bar(self, max_value):
        progress = GUIProgressBar(
            self.parent, orient=tk.HORIZONTAL,
            maximum=max_value,
            mode='determinate')
        progress.grid(row=0, column=0, columnspan=2, sticky='ews')
        progress.lift()
        return progress


class ScrolledWindow(tk.Frame):
    """
    https://stackoverflow.com/questions/16188420/tkinter-scrollbar-for-frame
    1. Master widget gets scrollbars and a canvas. Scrollbars are connected
    to canvas scrollregion.

    2. self.scrollwindow is created and inserted into canvas

    Usage Guideline:
    Assign any widgets as children of <ScrolledWindow instance>.scrollwindow
    to get them inserted into canvas

    __init__(self, parent, canv_w = 400, canv_h = 400, *args, **kwargs)
    docstring:
    Parent = master of scrolled window
    canv_w - width of canvas
    canv_h - height of canvas

    """
    def __init__(self, parent, canv_w=400, canv_h=400, xbar=False, ybar=True, *args, **kwargs):
        """Parent=master of scrolled window
        canv_w - width of canvas
        canv_h - height of canvas

       """
        super().__init__(parent, *args, **kwargs)
        # creating a canvas
        self.canv = tk.Canvas(self)
        self.canv.config(
            relief='flat',
            width=10,
            heigh=10, bd=2)
        # placing a canvas into frame
        self.canv.columnconfigure(0, weight=1)
        self.canv.grid(column=0, row=0, sticky='nsew')

        # creating a scrollbars
        if xbar:
            self.xscrlbr = ttk.Scrollbar(self,
                                         orient='horizontal',
                                         command=self.canv.xview)
            self.xscrlbr.grid(column=0, row=1, sticky='ew')
            self.canv.config(xscrollcommand=self.xscrlbr.set)

        if ybar:
            self.yscrlbr = ttk.Scrollbar(self,
                                         orient='vertical',
                                         command=self.canv.yview)
            self.yscrlbr.grid(column=1, row=0, sticky='ns')
            self.canv.config(yscrollcommand=self.yscrlbr.set)

        # creating a frame to inserto to canvas
        self.scrollwindow = ttk.Frame(self.canv)
        self.scrollwindow.bind('<Configure>', self._configure_window)
        self.scrollwindow.bind('<Enter>', self._bound_to_mousewheel)
        self.scrollwindow.bind('<Leave>', self._unbound_to_mousewheel)

        self.canv.create_window(0, 0, window=self.scrollwindow, anchor='nw')

        self.scrollwindow.columnconfigure(0, weight=1)
        # self.scrollwindow.grid(sticky='ew')

        if ybar:
            self.yscrlbr.lift(self.scrollwindow)
        if xbar:
            self.xscrlbr.lift(self.scrollwindow)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def _bound_to_mousewheel(self, event):
        self.canv.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbound_to_mousewheel(self, event):
        self.canv.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.canv.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _configure_window(self, event):
        size = (self.scrollwindow.winfo_reqwidth(), self.scrollwindow.winfo_reqheight())
        self.canv.config(scrollregion='0 0 %s %s' % size)


class Client(tk.Frame):
    OS_IMAGES = {
        'back': os.path.join('image', 'BackTile.png'),
        'pc': os.path.join('image', 'PcLogo.png'),
        'android': os.path.join('image', 'AndroidLogo.png'),
        'apple': os.path.join('image', 'AppleLogo.png'),
        'blackberry': os.path.join('image', 'BlackberryLogo.png'),
        'ip': os.path.join('image', 'IpLogo.png'),
        'linux': os.path.join('image', 'LinuxLogo.png'),
        'smartphone': os.path.join('image', 'SmartphoneLogo.png'),
        'unknown': os.path.join('image', 'UnknownLogo.png'),
        'windows': os.path.join('image', 'WindowsLogo.png'),
        'windowsphone': os.path.join('image', 'WindowsPhoneLogo.png'),
    }
    _node = None

    def __init__(self, parent, node, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        self._node = node
        self.cur_images = {}
        self.text = f'{node.get("user")}\n@{node["name"]}'

        if 'client' not in self.cur_images:
            back = Image.open(self.OS_IMAGES['back'])
            fore = Image.open(self.OS_IMAGES[node['operating_system']])
            image = Image.new("RGBA", (64, 64))
            image.alpha_composite(back)
            image.alpha_composite(fore)

            image = ImageTk.PhotoImage(image)
            self.cur_images['client'] = image
        else:
            image = self.cur_images['client']

        label_image = tk.Label(self, image=image)
        label_image.grid(row=0, column=0, rowspan=2, sticky='w')

        label_text = tk.Label(self, text=self.text, anchor='w', bg='white', justify=tk.LEFT)
        label_text.grid(row=0, column=1, sticky='ew')
        self.status = tk.StringVar()
        self.status.set('ready')
        label_status = tk.Label(self, textvariable=self.status, anchor='w', justify=tk.LEFT)
        label_status.grid(row=1, column=1, sticky='ew')

        self.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)

        # event_widgets = [self, label_image, label_text]
        event_widgets = [self, label_image, label_text, label_status]
        for widget in event_widgets:
            widget.bind('<Button-1>', self.click)
            widget.drop_target_register(tkdnd.DND_FILES, tkdnd.DND_TEXT)
            widget.dnd_bind('<<DropEnter>>', self.drop_enter)
            widget.dnd_bind('<<Drop>>', self.drop)
        self.send_count = -1

    def click(self, event):
        print('click', self.text)
        return
        if self.send_count >= 0:
            if self.send_count < self.send_max:
                self.send_count += 1
                # self.progress['value'] = self.send_count
                self.progress.step()
            else:
                self.send_count = -1
                self.progress.destroy()

    def drop_enter(self, event):
        event.widget.focus_force()
        return event.action

    def drop(self, event):
        if event.data:
            drop_files = self.drop_split(event.data)
            self.send_count = 0
            self.send_max = len(drop_files)
            self.send_files(drop_files)
        return event.action

    def drop_split(self, data):
        d_list = []
        sep = ' '
        for d in data.split(sep):
            if d.startswith('{'):
                d_list.append(d[1:])
            elif d.endswith('}'):
                d_list[-1] += (sep + d[:-1])
            else:
                d_list.append(d)
        return d_list

    def receive_files(self):
        print('receive')

    def send_files(self, files):
        client = GUINetDropClient(self)
        client.send_files(files)
        # print('send', self.text, files)


def bind_tree(widget, event, callback):
    widget.bind(event, callback)
    for child in widget.children.values():
        bind_tree(child, event, callback)


class GuiApp(tkdnd.Tk):
    _me = None

    def __init__(self, *args):
        super().__init__(*args)
        self.title = 'NDrop'
        self.geometry('280x360')
        self.queue = queue.SimpleQueue()

        frame = ScrolledWindow(self, xbar=True, ybar=True)
        frame.grid(sticky='ewns')
        self.frame = frame.scrollwindow

        uname = platform.uname()
        node = {}
        node['user'] = '(You)'
        node['name'] = uname.node
        node['operating_system'] = uname.system.lower()
        self._me = Client(self.frame, node)
        self._me.grid(row=0, column=0, sticky='ew', padx=10, pady=5)

        sep = ttk.Separator(self.frame)
        sep.grid(row=1, column=0, sticky='ew', pady=5, padx=40)

        node['user'] = 'IP connection'
        node['name'] = 'Send data to a remote device.'
        node['operating_system'] = 'ip'
        client = Client(self.frame, node)
        pad = (10, 5)
        client.grid(sticky='ew', padx=pad[0], pady=pad[1])

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.bind('<<queue_event>>', self.queue_handler)

    def queue_handler(self, event):
        item = self.queue.get_nowait()
        if item[0] == 'add_node':
            node = item[1]
            client = Client(self.frame, node)
            pad = (10, 5)
            client.grid(sticky='ew', padx=pad[0], pady=pad[1])
        elif item[0] == 'remove_node':
            node = item[1]
            for client in self.frame.winfo_children():
                if client._node['user'] == node['user'] and client._node['name'] == node['name']:
                    client.destroy()

    def run(self):
        listen = '0.0.0.0'
        mode = None
        cert = None
        key = None
        saved_dir = './'

        server = GUINetDropServer(self, listen, mode, (cert, key))
        server.saved_to(saved_dir)
        threading.Thread(
            name='Ndrop server',
            target=server.wait_for_request,
            daemon=True,
        ).start()

        self.mainloop()


def main():
    print(about.banner)
    app_logger = logging.getLogger(__name__.rpartition('.')[0])
    app_logger.setLevel(logging.INFO)

    FORMAT = ' * %(message)s'
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=FORMAT))
    app_logger.addHandler(handler)

    app = GuiApp()
    app.run()


if __name__ == '__main__':
    main()
