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


from . import about
from .netdrop import NetDropServer, NetDropClient

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
        self.parent.finish()


class GUINetDropServer(NetDropServer):
    def __init__(self, parent, *args):
        self.parent = parent
        super().__init__(*args)

    def init_bar(self, max_value):
        progress = GUIProgressBar(
            self.parent.owner, orient=ttk.HORIZONTAL,
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
        super().__init__(parent._node['ip'], parent._node['mode'].lower(), ssl_ck=(cert, key))

    def init_bar(self, max_value):
        progress = GUIProgressBar(
            self.parent, orient=ttk.HORIZONTAL,
            maximum=max_value,
            mode='determinate')
        progress.grid(row=1, column=1, sticky='ew')
        progress.lift()
        return progress


class ScrolledWindow(ttk.Frame):
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
            takefocus=0,
            borderwidth=0,
            highlightthickness=0,
            width=10,
            heigh=10)
        # placing a canvas into frame
        self.canv.columnconfigure(0, weight=1)
        self.canv.grid(column=0, row=0, sticky='nsew')
        self.canv.bind('<Configure>', self._configure_canvas)

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
        self.scrollwindow.columnconfigure(0, weight=1)

        self.item_window = self.canv.create_window(0, 0, window=self.scrollwindow, anchor='nw')

        if ybar:
            self.yscrlbr.lift(self.scrollwindow)
        if xbar:
            self.xscrlbr.lift(self.scrollwindow)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def _bound_to_mousewheel(self, event):
        # windows, macos
        self.canv.bind_all("<MouseWheel>", self._on_mousewheel)
        # linux
        self.canv.bind_all("<Button-4>", self._on_mousewheel)
        self.canv.bind_all("<Button-5>", self._on_mousewheel)

    def _unbound_to_mousewheel(self, event):
        self.canv.unbind_all("<MouseWheel>")
        self.canv.unbind_all("<Button-4>")
        self.canv.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        if sys.platform == 'darwin':
            # macos
            delta = -1 * event.delta
        elif event.num == 5:
            # linux up
            delta = 1
        elif event.num == 4:
            # linux down
            delta = -1
        else:
            # windows
            delta = -1 * (event.delta // 120)
        self.canv.yview_scroll(delta, "units")

    def _configure_window(self, event):
        # canvas will expand on both direction
        self.canv.configure(scrollregion=self.canv.bbox("all"))

    def _configure_canvas(self, event):
        self.canv.itemconfig(self.item_window, width=event.width)


class Client(ttk.Frame):
    image_dir = os.path.join(os.path.dirname(__file__), 'image')
    OS_IMAGES = {
        'back': os.path.join(image_dir, 'BackTile.png'),
        'pc': os.path.join(image_dir, 'PcLogo.png'),
        'android': os.path.join(image_dir, 'AndroidLogo.png'),
        'apple': os.path.join(image_dir, 'AppleLogo.png'),
        'blackberry': os.path.join(image_dir, 'BlackberryLogo.png'),
        'ip': os.path.join(image_dir, 'IpLogo.png'),
        'linux': os.path.join(image_dir, 'LinuxLogo.png'),
        'smartphone': os.path.join(image_dir, 'SmartphoneLogo.png'),
        'unknown': os.path.join(image_dir, 'UnknownLogo.png'),
        'windows': os.path.join(image_dir, 'WindowsLogo.png'),
        'windowsphone': os.path.join(image_dir, 'WindowsPhoneLogo.png'),
    }
    _node = None

    def __init__(self, parent, node, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        self._node = node

        back = Image.open(self.OS_IMAGES['back'])
        os_image = self.OS_IMAGES.get(node['operating_system']) or self.OS_IMAGES['unknown']
        fore = Image.open(os_image)
        image = Image.new("RGBA", (64, 64))
        image.alpha_composite(back)
        image.alpha_composite(fore)
        self.image = ImageTk.PhotoImage(image)

        self.style = ttk.Style()
        self.style.configure('client.TLabel', background='white')

        label_image = ttk.Label(self, image=self.image, style='client.TLabel')
        label_image.grid(row=0, column=0, rowspan=2, sticky='w')

        if node['mode'] == '?':
            self.text = f'{node.get("user")}\n@{node["name"]}'
        else:
            self.text = f'{node.get("mode")}\n@{node["name"]}'
        label_text = ttk.Label(self, text=self.text, anchor='w', style='client.TLabel', justify=tk.LEFT)
        label_text.grid(row=0, column=1, sticky='ew')

        self.status = tk.StringVar()
        if self._node['ip'] == '?':
            self.status.set('ready')
        else:
            self.status.set(f'{self._node["ip"]} - ready')
        label_status = ttk.Label(self, textvariable=self.status, anchor='w', style='client.TLabel', justify=tk.LEFT)
        label_status.grid(row=1, column=1, sticky='nsew')

        self.rowconfigure(1, weight=1)
        self.columnconfigure(1, weight=1)

        dnd_types = [tkdnd.DND_FILES, tkdnd.DND_TEXT]

        for widget in [self] + list(self.children.values()):
            widget.bind('<Button-1>', self.click)
            widget.drop_target_register(*dnd_types)
            widget.dnd_bind('<<DropEnter>>', self.drop_enter)
            widget.dnd_bind('<<DropPosition>>', self.drop_position)
            widget.dnd_bind('<<Drop:DND_Files>>', self.drop_files)
            widget.dnd_bind('<<Drop:DND_Text>>', self.drop_text)

    def bind_tree(self, widget, event, callback):
        widget.bind(event, callback)

        for child in widget.children.values():
            bind_tree(child, event, callback)

    def __str__(self):
        return '%(mode)s@%(name)s(%(ip)s)' % self._node

    def click(self, event):
        logger.info(self)

    def drop_position(self, event):
        if self._node['ip'] == '?':
            return tkdnd.REFUSE_DROP
        else:
            return event.action

    def drop_enter(self, event):
        event.widget.focus_force()
        return event.action

    def drop_text(self, event):
        if event.data:
            self.send_text(event.data)
            return tkdnd.COPY

    def drop_files(self, event):
        if event.data:
            drop_files = self.tk.splitlist(event.data)
            self.send_files(drop_files)
            return tkdnd.COPY

    def send_text(self, text):
        agent = GUINetDropClient(self)
        threading.Thread(
            name='Ndrop client',
            target=agent.send_text,
            args=(text, ),
        ).start()

    def send_files(self, files):
        agent = GUINetDropClient(self)
        threading.Thread(
            name='Ndrop client',
            target=agent.send_files,
            args=(files, ),
        ).start()

    def finish(self):
        self.status.set(f'{self._node["mode"]} - done')
        self.agent = None


def bind_tree(widget, event, callback):
    widget.bind(event, callback)
    for child in widget.children.values():
        bind_tree(child, event, callback)


class GuiApp(tkdnd.Tk):
    owner = None
    unknown_client = None

    def __init__(self, *args):
        super().__init__(*args)
        self.title('%s v%s' % (about.name.capitalize(), about.version))

        image_dir = os.path.join(os.path.dirname(__file__), 'image')
        icon_path = os.path.join(image_dir, 'ndrop.png')
        image = Image.open(icon_path)
        self.image = ImageTk.PhotoImage(image)
        self.iconphoto(False, self.image)

        self.geometry('320x360')
        self.queue = queue.SimpleQueue()

        uname = platform.uname()
        owner_node = {}
        owner_node['user'] = 'You'
        owner_node['name'] = uname.node
        owner_node['operating_system'] = uname.system.lower()
        owner_node['mode'] = '?'
        owner_node['ip'] = '?'
        self.owner = Client(self, owner_node)
        self.owner.grid(row=0, column=0, sticky='ew', padx=10, pady=10)

        sep = ttk.Separator(self)
        sep.grid(row=1, column=0, sticky='ew', padx=40, pady=0)

        frame = ScrolledWindow(self, xbar=False, ybar=True)
        frame.grid(sticky='ewns')
        self.frame = frame.scrollwindow

        unknown_node = {}
        unknown_node['user'] = 'IP connection'
        unknown_node['name'] = 'Send data to a remote device.'
        unknown_node['operating_system'] = 'ip'
        unknown_node['mode'] = '?'
        unknown_node['ip'] = '?'
        self.unknown_client = Client(self.frame, unknown_node)
        self.unknown_client.grid(sticky='ew', padx=10, pady=5)

        self.rowconfigure(2, weight=1)
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


def run():
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
    run()
