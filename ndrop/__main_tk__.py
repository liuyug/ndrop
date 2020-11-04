#!/usr/bin/env python3
# -*- encoding:utf-8 -*-

import os
import sys
import platform
import re
import threading
import queue
import webbrowser
import logging

from PIL import Image, ImageTk
import tkinterdnd2 as tkdnd
import tkinter as tk
import tkinter.ttk as ttk
from tkinter.simpledialog import Dialog
from tkinter.messagebox import showinfo
from tkinter.filedialog import askdirectory
import appdirs

from . import init_config, save_config, gConfig
from . import hdpitk
from . import about
from .netdrop import NetDropServer, NetDropClient
from .transport import get_broadcast_address, human_size

logger = logging.getLogger(__name__)


class GUIProgressBar(ttk.Progressbar):
    def __init__(self, parent, **kwargs):
        self.parent = parent
        self.style = style = ttk.Style()
        # add label in the layout
        style.layout(
            'text.Horizontal.TProgressbar',
            [
                (
                    'Horizontal.Progressbar.trough',
                    {
                        'children': [
                            ('Horizontal.Progressbar.pbar', {'side': 'left', 'sticky': 'ns'})
                        ],
                        'sticky': 'nswe'
                    }
                ),
                (
                    'Horizontal.Progressbar.label',
                    {'sticky': ''}
                ),
            ]
        )
        super().__init__(parent, style='text.Horizontal.TProgressbar', **kwargs)
        self.interval = 100
        self.step_count = 0
        self.time_index = 0
        self.count = [0] * (1000 // self.interval)
        self.speed = f'{human_size(sum(self.count)):>9}/s'
        style.configure('text.Horizontal.TProgressbar', text=self.speed)
        self.parent.after(self.interval, self.on_timer_update)

    def on_timer_update(self):
        if self.step_count >= 0:
            self.parent.after(self.interval, self.on_timer_update)
            self.speed = f'{human_size(sum(self.count)):>9}/s'
            self.count[self.time_index] = self.step_count
            self.step_count = 0
            # 0 ~ 9
            self.time_index = (self.time_index + 1) % (1000 // self.interval)

    def update(self, step):
        self.step_count += step
        self.parent.on_progressbar_update(step)
        self.style.configure('text.Horizontal.TProgressbar', text=self.speed)

    def write(self, message, file=None):
        logger.info(message)

    def close(self):
        logger.info('done')
        self.step_count = -1
        self.parent.on_progressbar_close(self.speed.strip())


class GUINetDropServer(NetDropServer):
    def __init__(self, parent, *args):
        self.parent = parent
        super().__init__(*args)

    def init_bar(self, max_value):
        progress = GUIProgressBar(
            self.parent.owner, orient=tk.HORIZONTAL,
            maximum=max_value,
            mode='determinate')
        progress.grid(row=1, column=1, sticky='nsew')
        progress.lift()
        self.parent.owner.progress = progress
        return progress

    def add_node(self, node):
        self.parent.queue.put_nowait(('add_node', node))
        self.parent.event_generate('<<server_queue_event>>')

    def remove_node(self, node):
        self.parent.queue.put_nowait(('remove_node', node))
        self.parent.event_generate('<<server_queue_event>>')


class GUINetDropClient(NetDropClient):
    def __init__(self, parent, ip, mode, cert=None, key=None):
        self.parent = parent
        super().__init__(ip, mode.lower(), ssl_ck=(cert, key))

    def init_bar(self, max_value):
        progress = GUIProgressBar(
            self.parent, orient=tk.HORIZONTAL,
            maximum=max_value,
            mode='determinate')
        progress.grid(row=1, column=1, sticky='nsew')
        progress.lift()
        self.parent.progress = progress
        return progress


IMAGES = {
    'back': 'BackTile.png',
    'pc': 'PcLogo.png',
    'android': 'AndroidLogo.png',
    'apple': 'AppleLogo.png',
    'blackberry': 'BlackberryLogo.png',
    'ip': 'IpLogo.png',
    'linux': 'LinuxLogo.png',
    'smartphone': 'SmartphoneLogo.png',
    'unknown': 'UnknownLogo.png',
    'windows': 'WindowsLogo.png',
    'windowsphone': 'WindowsPhoneLogo.png',
    'config': 'ConfigIcon.png',
    'openfolder': 'OpenFolderIcon.png',
}


class NdropImage():
    @classmethod
    def get_os_image(cls, name):
        image_dir = os.path.join(os.path.dirname(__file__), 'image')

        back_path = os.path.join(image_dir, IMAGES['back'])
        back_im = Image.open(back_path)

        fore_path = os.path.join(
            image_dir,
            IMAGES.get(name) or IMAGES['unknown']
        )
        fore_im = Image.open(fore_path)

        image = Image.new("RGBA", fore_im.size)
        image.alpha_composite(back_im.resize(fore_im.size))
        image.alpha_composite(fore_im)
        return ImageTk.PhotoImage(image)

    @classmethod
    def get_image(cls, name, background=None):
        image_dir = os.path.join(os.path.dirname(__file__), 'image')

        fore_path = os.path.join(image_dir, IMAGES[name])
        fore_im = Image.open(fore_path)

        background = background or 'white'

        image = Image.new("RGBA", fore_im.size, color=background)
        image.alpha_composite(fore_im)
        return ImageTk.PhotoImage(image)


class AutoScrollbar(ttk.Scrollbar):
    # a scrollbar that hides itself if it's not needed.  only
    # works if you use the grid geometry manager.
    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            # grid_remove is currently missing from Tkinter!
            self.tk.call("grid", "remove", self)
        else:
            self.grid()
        super().set(lo, hi)

    def pack(self, **kw):
        raise tk.TclError("cannot use pack with this widget")

    def place(self, **kw):
        raise tk.TclError("cannot use place with this widget")


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
            self.xscrlbr = AutoScrollbar(self,
                                         orient='horizontal',
                                         command=self.canv.xview)
            self.xscrlbr.grid(column=0, row=1, sticky='ew')
            self.canv.config(xscrollcommand=self.xscrlbr.set)

        if ybar:
            self.yscrlbr = AutoScrollbar(self,
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
    node = None

    def __init__(self, parent, node, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent = parent
        self.node = node

        self.queue = queue.SimpleQueue()
        self.virtual_event = '<<client_queue_event>>'
        self.bind(self.virtual_event, self.queue_handler)

        self.image = NdropImage.get_os_image(node['operating_system'])

        self.style = ttk.Style()
        self.style.configure('client.TLabel', background='white')

        label_image = ttk.Label(self, image=self.image, style='client.TLabel')
        label_image.grid(row=0, column=0, rowspan=2, sticky='w')

        if node['mode'] == '?':
            text = f'{node.get("user")}\n@{node["name"]}'
        else:
            text = f'{node.get("mode")}\n@{node["name"]}'
        label_text = ttk.Label(
            self, text=text,
            anchor='w', style='client.TLabel', justify=tk.LEFT)
        label_text.grid(row=0, column=1, sticky='ew')

        self.status = tk.StringVar()
        if self.node['ip'] == '?':
            self.status.set('ready')
        else:
            self.status.set(f'{self.node["ip"]} - ready')
        label_status = ttk.Label(
            self, textvariable=self.status,
            anchor='w', style='client.TLabel', justify=tk.LEFT)
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
        return '%(mode)s@%(name)s(%(ip)s)' % self.node

    def queue_handler(self, event):
        item = self.queue.get_nowait()
        if getattr(self, 'progress'):
            if item[0] == 'step':
                self.progress.step(item[1])
            elif item[0] == 'close':
                self.progress.destroy()
                self.progress = None
                self.status.set(f'{self.node["ip"]} - done - {item[1]}')

    def on_progressbar_update(self, step):
        self.queue.put_nowait(('step', step))
        self.event_generate(self.virtual_event)

    def on_progressbar_close(self, speed):
        self.queue.put_nowait(('close', speed))
        self.event_generate(self.virtual_event)

    def click(self, event):
        if self.node['owner'] == 'unknown':
            dlg = IPSendDialog(self.master, 'IP connection',
                               ip=self.node['ip'],
                               mode=self.node['mode'])
            if dlg.result and dlg.result[0]:
                self.node['ip'] = dlg.result[0]
                self.node['mode'] = dlg.result[1]
                self.status.set(f'{self.node["ip"]} - ready')
        else:
            logger.info(self)

    def drop_position(self, event):
        if self.node.get('owner') == 'self' or self.node.get('ip') == '?':
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
        agent = GUINetDropClient(self, self.node['ip'], self.node['mode'])
        threading.Thread(
            name='Ndrop client',
            target=agent.send_text,
            args=(text, ),
        ).start()

    def send_files(self, files):
        agent = GUINetDropClient(self, self.node['ip'], self.node['mode'])
        threading.Thread(
            name='Ndrop client',
            target=agent.send_files,
            args=(files, ),
        ).start()


class SettingDialog(Dialog):
    def __init__(self, master, title=None, **kwargs):
        target_dir = kwargs.get('target_dir', '')
        self.target_dir = tk.StringVar()
        self.target_dir.set(target_dir)

        hdpi = 1 if kwargs.get('enable_hdpi') else 0
        self.hdpi = tk.IntVar()
        self.hdpi.set(hdpi)

        super().__init__(master, title)

    def body(self, master):
        label = ttk.Label(master, text='Saved folder:')
        label.grid(row=0, sticky='w')

        entry = ttk.Entry(master, textvariable=self.target_dir, width=40)
        entry.grid(row=1, column=0, sticky='ew')

        button = ttk.Button(master, text='Change folder')
        button.grid(row=2, column=0, sticky='e')
        button.bind('<Button-1>', self.change_folder)

        checkbox = ttk.Checkbutton(master, text='Enable HDPI', variable=self.hdpi)
        checkbox.grid(row=3, column=0, sticky='ew')

        master.rowconfigure(1, weight=1)
        master.columnconfigure(0, weight=1)
        master.pack(fill=tk.BOTH)

    def buttonbox(self):
        """replace origin wdiget with ttk"""
        box = ttk.Frame(self)

        w = ttk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE)
        w.pack(side=tk.LEFT, padx=5, pady=5)
        w = ttk.Button(box, text="Cancel", width=10, command=self.cancel)
        w.pack(side=tk.LEFT, padx=5, pady=5)

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()

    def apply(self):
        target_dir = self.target_dir.get()
        hdpi = self.hdpi.get()
        self.result = os.path.normpath(target_dir), hdpi == 1

    def change_folder(self, event):
        folder = askdirectory(initialdir=self.target_dir.get())
        if folder:
            self.target_dir.set(folder)


class IPSendDialog(Dialog):
    def __init__(self, master, title=None, ip=None, mode=None, **kwargs):
        self.dest_ip = tk.StringVar()
        if ip and ip != '?':
            self.dest_ip.set(ip)
        self.mode = tk.StringVar()
        if mode and mode != '?':
            self.mode.set(mode)
        super().__init__(master, title)

    def body(self, master):
        label = ttk.Label(master, text='IP Address:')
        label.grid(row=0, column=0, sticky='w')

        entry = ttk.Entry(master, textvariable=self.dest_ip, width=20)
        entry.grid(row=0, column=1, sticky='ew')

        label = ttk.Label(master, text='Mode:')
        label.grid(row=1, column=0, sticky='w')

        choices = ['Dukto', 'NitroShare']
        if not self.mode.get():
            self.mode.set(choices[0])
        combo = ttk.Combobox(master, values=choices, textvariable=self.mode, state="readonly")
        combo.grid(row=1, column=1, sticky='ew')

        # master.rowconfigure(1, weight=1)
        master.columnconfigure(1, weight=1)
        master.pack(fill=tk.BOTH)
        return entry

    def buttonbox(self):
        """replace origin wdiget with ttk"""
        box = ttk.Frame(self)

        w = ttk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE)
        w.pack(side=tk.LEFT, padx=5, pady=5)
        w = ttk.Button(box, text="Cancel", width=10, command=self.cancel)
        w.pack(side=tk.LEFT, padx=5, pady=5)

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()

    def apply(self):
        dest_ip = self.dest_ip.get()
        mode = self.mode.get()
        self.result = (dest_ip, mode)


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
        icon_path = os.path.join(image_dir, 'ndrop.ico')
        self.iconphoto(True, ImageTk.PhotoImage(Image.open(icon_path)))

        self.geometry('320x360')
        self.queue = queue.SimpleQueue()

        uname = platform.uname()
        ipaddrs, _ = get_broadcast_address()
        owner_node = {}
        owner_node['user'] = 'You'
        owner_node['name'] = uname.node
        owner_node['operating_system'] = uname.system.lower()
        owner_node['mode'] = '?'
        owner_node['ip'] = ', '.join(ipaddrs)
        owner_node['owner'] = 'self'
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
        unknown_node['owner'] = 'unknown'
        self.unknown_client = Client(self.frame, unknown_node)
        self.unknown_client.grid(sticky='ew', padx=10, pady=5)

        s = ttk.Style()
        s.configure('footer.TFrame', background='green')
        s.configure('footer.TLabel', background='green')

        footer = ttk.Frame(self, style='footer.TFrame')
        footer.grid(sticky='ew')

        self.image_openfolder = NdropImage.get_image('openfolder', background='green')
        label = ttk.Label(footer, image=self.image_openfolder, style='footer.TLabel')
        label.grid(row=0, column=1, padx=10, pady=5)
        label.bind('<Button-1>', self.open_folder)

        self.image_config = NdropImage.get_image('config', background='green')
        label = ttk.Label(footer, image=self.image_config, style='footer.TLabel')
        label.grid(row=0, column=2, padx=10, pady=5)
        label.bind('<Button-1>', self.show_config)

        footer.columnconfigure(0, weight=1)
        footer.columnconfigure(3, weight=1)

        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        self.bind('<<server_queue_event>>', self.queue_handler)

    def open_folder(self, event):
        webbrowser.open(gConfig.app['target_dir'])

    def show_config(self, event):
        dlg = SettingDialog(
            self, 'Settings',
            target_dir=gConfig.app['target_dir'],
            enable_hdpi=gConfig.app['enable_hdpi'],
        )
        if dlg.result:
            target_dir, hdpi = dlg.result
            if gConfig.app['enable_hdpi'] != hdpi:
                showinfo('Information', 'Close and open app again to enable HDPI')
            gConfig.app['target_dir'] = target_dir
            gConfig.app['enable_hdpi'] = hdpi
            save_config()

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
                if client.node['user'] == node['user'] and client.node['name'] == node['name']:
                    client.destroy()

    def run(self):
        listen = '0.0.0.0'
        mode = None
        cert = None
        key = None

        self.server = GUINetDropServer(self, listen, mode, (cert, key))
        self.server.saved_to(gConfig.app['target_dir'])
        threading.Thread(
            name='Ndrop server',
            target=self.server.wait_for_request,
            daemon=True,
        ).start()

        self.mainloop()


def run():
    print(about.banner)
    init_config()
    app_logger = logging.getLogger(__name__.rpartition('.')[0])
    app_logger.setLevel(logging.INFO)

    FORMAT = ' * %(message)s'
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt=FORMAT))
    app_logger.addHandler(handler)

    app = GuiApp()
    if gConfig.app.get('enable_hdpi'):
        hdpitk.MakeTkDPIAware(app)
    app.run()


if __name__ == '__main__':
    run()
