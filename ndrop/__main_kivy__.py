#!/usr/bin/env python3
# -*- encoding:utf-8 -*-

import os.path
import sys
import argparse
import logging
import platform
import ipaddress
import threading
import queue
import webbrowser
from functools import partial

from . import init_config, save_config, gConfig
from . import about
from . import hfs
from .netdrop import NetDropServer, NetDropClient
from .transport import get_broadcast_address, human_size

from .image import NdropImage

from kivy.app import App
from kivy.config import Config
from kivy.logger import Logger
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.resources import resource_add_path, resource_find
from kivy.uix.behaviors.button import ButtonBehavior
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.graphics import Color, Rectangle
from kivy.core.image import Image as CoreImage
from kivy.graphics.texture import Texture
from kivy.properties import StringProperty, ObjectProperty
from kivy.utils import platform as kivy_platform

from kivy_garden.filebrowser import FileBrowser


logger = logging.getLogger(__name__)


class GUIProgressBar(ProgressBar):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.interval = 100
        self.step_count = 0
        self.time_index = 0
        self.speed = ''
        self.count = [0] * (1000 // self.interval)

    def __repr__(self):
        return '<GUIProgressBar>'

    def update_bar(self, *args):
        self.value = self.step_count

    def update(self, step):
        self.step_count += step
        Clock.schedule_once(self.update_bar)

    def write(self, message, file=None):
        logger.info(message)

    def close(self):
        if not self.speed:
            # transfer complete less than a second
            self.count[self.time_index] = self.step_count
            speed = sum(self.count) / (len([x for x in self.count if x != 0]) * self.interval / 1000)
            self.speed = f'{human_size(speed):>9}/s'
        self.step_count = 0


class GUINetDropServer(NetDropServer):
    def __init__(self, parent, *args):
        self.parent = parent
        super().__init__(*args)

    def init_widget(self, *args):
        pb = self.parent.root.ids.you.progress
        pb.max = self.max_value

    def init_bar(self, max_value):
        App.get_running_app().ask_runtime_permission('WRITE_EXTERNAL_STORAGE')
        pb = self.parent.root.ids.you.progress
        self.max_value = max_value
        Clock.schedule_once(self.init_widget)
        return pb

    def add_node(self, node):
        """add_node
        receive mess from network and notify gui
        """
        super().add_node(node)
        self.parent.on_add_node(node)

    def remove_node(self, node):
        super().remove_node(node)
        self.parent.on_remove_node(node)

    def recv_finish_text(self, from_addr):
        text = super().recv_finish_text(from_addr)
        self.parent.on_recv_text(text, from_addr)
        return text

    def recv_finish_file(self, path, from_addr):
        super().recv_finish_file(path, from_addr)

    def recv_finish(self, from_addr, err):
        self.parent.root.ids.you.recv_finish(from_addr, err)
        super().recv_finish(from_addr, err)


class GUINetDropClient(NetDropClient):
    def __init__(self, parent, ip, mode, cert=None, key=None):
        self.parent = parent
        super().__init__(ip, mode.lower(), ssl_ck=(cert, key))

    def init_widget(self, *args):
        pb = self.parent.ids.progress
        pb.max = self.max_value

    def init_bar(self, max_value):
        pb = self.parent.ids.progress
        self.max_value = max_value
        Clock.schedule_once(self.init_widget)
        return pb

    def send_finish_file(self, path):
        super().send_finish_file(path)

    def send_finish(self, err):
        self.parent.send_finish(err)
        super().send_finish(err)


class ButtonLabel(ButtonBehavior, Label):
    def __repr__(self):
        return '<ButtonLabel>'


class SendWidget(BoxLayout):
    dismiss = ObjectProperty(None)

    def __init__(self, ip=None, mode=None, **kwargs):
        super().__init__(**kwargs)
        self.ip = ip
        self.mode = mode
        Clock.schedule_once(self.init_widget)

    def init_widget(self, dt):
        if not self.ip or self.ip == '?':
            self.ids.send_text.disabled = True
            self.ids.send_files.disabled = True
        else:
            self.ids.ip.text = self.ip
            self.ids.ip.disabled = True
        if self.mode == 'Dukto':
            self.ids.dukto.active = True
        elif self.mode == 'NitroShare':
            self.ids.nitroshare.active = True
        else:
            self.ids.dukto.active = True

    def on_open(self):
        if not self.ids.ip.text:
            self.ids.ip.focus = True
        else:
            self.ids.message.focus = True

    def on_input_text(self, widget):
        if widget.text:
            if self.ids.dukto.active:
                self.ids.send_text.disabled = False
            self.ids.send_files.disabled = False
        else:
            self.ids.send_text.disabled = True
            self.ids.send_files.disabled = True

    def on_checkbox_press(self, widget, *args):
        if widget.active:
            return
        widget.active = True

    def on_checkbox_active(self, widget, *args):
        if not widget.active:
            return
        if widget.text == 'nitroshare':
            self.ids.send_text.disabled = True
            self.ids.message.disabled = True
        if widget.text == 'dukto':
            if self.ids.ip.text:
                self.ids.send_text.disabled = False
            self.ids.message.disabled = False

    def on_send_text(self):
        ip = self.ids.ip.text
        if not ip or ip == '?':
            return
        if self.ids.dukto.active:
            mode = 'Dukto'
        elif self.ids.nitroshare.active:
            mode = 'Nitroshare'
        else:
            raise ValueError()
        text = self.ids.message.text
        self.do_send_text(text, ip, mode)
        self.dismiss()

    def on_get_files(self, path, files):
        for f in files:
            f = os.path.join(path, f)
        self.on_send_files2(files)

    def on_send_files(self):
        FileChooserWidget.ask_files(
            path=gConfig.app['target_dir'],
            callback=self.on_get_files,
        )

    def on_send_files2(self, files):
        ip = self.ids.ip.text
        if not ip or ip == '?':
            return
        if self.ids.dukto.active:
            mode = 'Dukto'
        elif self.ids.nitroshare.active:
            mode = 'Nitroshare'
        else:
            raise ValueError()
        self.do_send_files(files, ip, mode)
        self.dismiss()


class ClientWidget(ButtonBehavior, BoxLayout):
    progress = None
    popup_sendmessage = None
    node = ObjectProperty(None)
    image_name = StringProperty()

    def __init__(self, node=None, **kwargs):
        super(ClientWidget, self).__init__(**kwargs)
        self.node = node

    def __repr__(self):
        if self.node:
            return '<ClientWidget: %(user)s %(mode)s@%(name)s - %(ip)s>' % self.node
        else:
            return '<ClientWidget: NULL>'

    def on_image_name(self, instance, name):
        bio = NdropImage.get_os_pngio(name)
        self.texture = CoreImage(bio, ext='png').texture

    def on_node(self, instance, node):
        # self.node = node
        if node['mode'] == '?':
            self.user = node['user']
        else:
            self.user = node['mode']
        self.name = '@%(name)s' % node
        if node['ip'] == '?':
            self.message = 'ready'
        else:
            self.message = '%(ip)s - ready' % node
        self.image_name = node['operating_system']
        self.progress = self.ids.progress

    def do_send_files(self, files, ip=None, mode=None):
        ip = ip or self.node['ip']
        mode = mode or self.node['mode']
        agent = GUINetDropClient(self, ip, mode)
        threading.Thread(
            name='Ndrop client',
            target=agent.send_files,
            args=(files, ),
        ).start()

    def update_message(self, dt, err):
        self.message = '%s - %s' % (self.node['ip'], err)

    def send_finish(self, err):
        """被GUINetDropClient调用，通知本次发送任务完成"""
        if err == 'done':
            err = 'ready'
        Clock.schedule_once(partial(self.update_message, err=err))

    def recv_finish(self, from_addr, err):
        """被GUINetDropServer调用，通知本次接收任务完成"""
        if err == 'done':
            err = 'ready'
        Clock.schedule_once(partial(self.update_message, err=err))

    def do_send_text(self, text, ip=None, mode=None):
        ip = ip or self.node['ip']
        mode = mode or self.node['mode']
        agent = GUINetDropClient(self, ip, mode)
        threading.Thread(
            name='Ndrop client',
            target=agent.send_text,
            args=(text, ),
        ).start()

    def on_press(self):
        if self.node['type'] == 'host':
            return
        if not self.popup_sendmessage:
            content = SendWidget(ip=self.node['ip'], mode=self.node['mode'])
            self.popup_sendmessage = Popup(
                title="Send",
                title_color=(0, 0, 0, 1),
                content=content,
                auto_dismiss=False,
                background='',
            )
            self.popup_sendmessage.on_open = content.on_open
            content.dismiss = self.popup_sendmessage.dismiss
            content.do_send_text = self.do_send_text
            content.do_send_files = self.do_send_files
        self.popup_sendmessage.open()


class RootWidget(BoxLayout):
    messagebox = None
    popup_hfs = None
    popup_messagebox = None
    popup_config = None

    def __init__(self, **kwargs):
        super(RootWidget, self).__init__(**kwargs)
        self.register_event_type('on_ndrop_event')

    def init_widget(self, *args):
        self.messagebox = MessageWidget()
        app = App.get_running_app()
        self.ids.you.node = app.host_node
        self.ids.ip.node = app.ip_node
        Clock.schedule_once(app.remove_android_splash)

    def on_drop_file(self, widget, text, x, y, *args):
        # 当拖拽多个文件，会产生多个事件，每个事件一个文件
        filename = text.decode('utf-8')
        wx, wy = self.ids.scroll_layout.to_widget(*Window.mouse_pos)
        for client in self.ids.scroll_layout.children:
            if client.collide_point(wx, wy):
                client.do_send_files([filename])

    def on_drop_text(self, widget, text, x, y, *args):
        text = text.decode('utf-8')
        wx, wy = self.ids.scroll_layout.to_widget(*Window.mouse_pos)
        for client in self.ids.scroll_layout.children:
            if client.collide_point(wx, wy):
                client.do_send_text(text)

    def add_client(self, dt, node):
        client = ClientWidget(node)
        self.ids.scroll_layout.add_widget(client)
        Logger.info(f'{about.name}: add {client}')

    def remove_client(self, dt, client):
        self.ids.scroll_layout.remove_widget(client)
        Logger.info(f'{about.name}: remove {client}')

    def recv_text(self, dt, text):
        self.messagebox.append_text(text)
        if not self.popup_messagebox:
            self.popup_messagebox = Popup(
                title="MessageBox",
                title_color=(0, 0, 0, 1),
                content=self.messagebox,
                auto_dismiss=False,
                background='',
            )
            self.messagebox.dismiss = self.popup_messagebox_dismiss
            self.is_messagebox_open = False
        # 被动打开窗口
        if not self.is_messagebox_open:
            self.popup_messagebox.open()
            self.is_messagebox_open = True

    def popup_messagebox_dismiss(self):
        self.popup_messagebox.dismiss()
        self.is_messagebox_open = False

    def on_ndrop_event(self, args):
        layout = self.ids.scroll_layout
        if args['action'] == 'add_node':
            node = args['node']
            for client in layout.children:
                if client.node['ip'] == node['ip'] and \
                        client.node['mode'] == node['mode']:
                    if client.node['type'] == 'text' and node['type'] == 'guest':
                        # destroy text client and create guest client
                        Clock.schedule_once(partial(self.remove_client, client=client))
                    else:
                        # client is exists
                        return True
            Clock.schedule_once(partial(self.add_client, node=node))
            return True
        elif args['action'] == 'remove_node':
            node = args['node']
            for client in layout.children:
                if client.node['type'] == 'guest' and \
                        client.node['ip'] == node['ip'] and \
                        client.node['mode'] == node['mode']:
                    Clock.schedule_once(partial(self.remove_client, client=client))
            return True
        elif args['action'] == 'recv_text':
            text = args['text']
            ip, port = args['from_addr']
            if gConfig.app['create_node_by_text']:
                # add node
                recv_node = {}
                recv_node['user'] = 'Unknown'
                recv_node['name'] = 'Unknown'
                recv_node['operating_system'] = 'ip'
                recv_node['mode'] = 'Dukto'
                recv_node['ip'] = ip
                recv_node['type'] = 'text'
                self.dispatch('on_ndrop_event', {
                    'action': 'add_node',
                    'node': recv_node,
                })
            message = f'{ip}: {text}'
            Logger.info(f'{about.name} TEXT: {message}')
            Clock.schedule_once(partial(self.recv_text, text=message))
            return True

    def open_folder(self):
        App.get_running_app().ask_runtime_permission('READ_EXTERNAL_STORAGE')
        file_url = 'file://%s' % gConfig.app['target_dir']
        webbrowser.open(file_url)

    def show_config(self):
        if not self.popup_config:
            content = ConfigWidget()
            self.popup_config = Popup(
                title="Config",
                title_color=(0, 0, 0, 1),
                content=content,
                auto_dismiss=False,
                background='',
            )
            content.dismiss = self.popup_config.dismiss
        self.popup_config.open()

    def show_hfs(self):
        if not self.popup_hfs:
            content = HFSWidget()
            self.popup_hfs = Popup(
                title="HFS",
                title_color=(0, 0, 0, 1),
                content=content,
                auto_dismiss=False,
                background='',
            )
            content.dismiss = self.popup_hfs.dismiss
        self.popup_hfs.open()


class CheckLabelBox(BoxLayout):
    def on_checkbox_active(self, cb):
        self.active = cb.active

    def on_label_click(self, cb):
        cb.active = not cb.active


class FileChooserWidget(FloatLayout):
    path = StringProperty()
    callback = None
    select = ObjectProperty(None)
    cancel = ObjectProperty(None)

    def __init__(self, path=None, **kwargs):
        super().__init__(**kwargs)
        self.path = path
        Clock.schedule_once(self.init_widget)

    def init_widget(self, *args):
        self.ids.filechooser.path = self.path
        self.ids.filechooser.bind(on_entry_added=self.update_file_list_entry)
        self.ids.filechooser.bind(on_subentry_to_entry=self.update_file_list_entry)

    def update_file_list_entry(self, file_chooser, file_list_entry, *args):
        for layout in file_list_entry.children:
            for label in layout.children:
                label.color = (0, 0, 0, 1)

    def select(self, path, files):
        if self.callback:
            self.callback(path, files)
        self.popup.dismiss()

    @staticmethod
    def ask_files(path=None, callback=None):
        App.get_running_app().ask_runtime_permission('READ_EXTERNAL_STORAGE')
        # 当选择多个文件时，List视图不能显示选中的文件
        content = FileChooserWidget(path=path)
        popup = Popup(
            title="Select folder",
            title_color=(0, 0, 0, 1),
            content=content,
            auto_dismiss=False,
            background='',
        )
        content.popup = popup
        content.callback = callback
        content.cancel = popup.dismiss
        popup.open()


class ConfigWidget(BoxLayout):
    dismiss = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self.init_widget)

    def init_widget(self, *args):
        self.ids.target_dir.text = gConfig.app['target_dir']
        self.ids.create_node_by_text.active = gConfig.app['create_node_by_text']

    def on_get_folder(self, path, files):
        self.ids.target_dir.text = path

    def on_change_folder(self):
        FileChooserWidget.ask_files(
            path=gConfig.app['target_dir'],
            callback=self.on_get_folder,
        )

    def on_ok(self):
        gConfig.app['target_dir'] = self.ids.target_dir.text
        gConfig.app['create_node_by_text'] = self.ids.create_node_by_text.active
        save_config()
        app = App.get_running_app()
        app.server.saved_to(gConfig.app['target_dir'])
        self.dismiss()

    def on_cancel(self):
        self.dismiss()


class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(record)


class MessageWidget(BoxLayout):
    dismiss = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def append_text(self, text):
        self.ids.log.do_cursor_movement('cursor_end', control=True)
        self.ids.log.readonly = False
        self.ids.log.insert_text(f'{text}\n')
        self.ids.log.readonly = True

    def on_ok(self):
        self.dismiss()


class HFSWidget(BoxLayout):
    dismiss = ObjectProperty(None)

    def __init__(self, **kwargs):
        super(HFSWidget, self).__init__(**kwargs)
        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)

        formatter = logging.Formatter('%(message)s')
        self.queue_handler.setFormatter(formatter)

        hfs_logger = logging.getLogger('%s.hfs' % __name__.rpartition('.')[0])
        hfs_logger.addHandler(self.queue_handler)

        Logger.info('HFS: -- HFS server start --')
        listen = '0.0.0.0'
        cert = None
        key = None
        self.hfs_server = hfs.start(listen,
                  root_path=gConfig.app['target_dir'],
                  cert=cert, key=key,
                  daemon=True)
        Clock.schedule_once(self.on_clock_check)

    def append_text(self, text):
        # Logger.info(f'HFS: {text}')
        self.ids.log.do_cursor_movement('cursor_end', control=True)
        self.ids.log.readonly = False
        self.ids.log.insert_text(f'{text}\n')
        self.ids.log.readonly = True

    def on_clock_check(self, dt):
        while True:
            try:
                record = self.log_queue.get(block=False)
            except queue.Empty:
                break
            else:
                text = self.queue_handler.format(record)
                self.append_text(text)
        if self.hfs_server:
            Clock.schedule_once(self.on_clock_check)

    def on_ok(self):
        self.hfs_server.shutdown()
        self.hfs_server = None
        Logger.info('HFS: -- HFS server close --')
        self.dismiss()


class GuiApp(App):
    host_node = None
    ip_node = None

    def build(self):
        kv_dir = os.path.dirname(__file__)
        self.image_dir = os.path.join(kv_dir, 'image')

        self.title = '%s v%s' % (about.name.capitalize(), about.version)
        self.icon = os.path.join(self.image_dir, 'ndrop.png')
        self.load_kv(os.path.join(kv_dir, '__main_kivy__.kv'))

        uname = platform.uname()
        ipaddrs, _ = get_broadcast_address()
        host_node = {}
        host_node['user'] = 'You'
        host_node['name'] = uname.node
        host_node['operating_system'] = uname.system
        host_node['mode'] = '?'
        host_node['ip'] = ', '.join(ipaddrs)
        host_node['type'] = 'host'
        self.host_node = host_node

        ip_node = {}
        ip_node['user'] = 'IP connection'
        ip_node['name'] = 'Send data to a remote device.'
        ip_node['operating_system'] = 'Unknown'
        ip_node['mode'] = '?'
        ip_node['ip'] = '?'
        ip_node['type'] = 'ip'
        self.ip_node = ip_node

        self.client_node = []

        self.root = RootWidget()
        self.root.init_widget()
        self.start_ndrop_server()
        Window.bind(on_drop_file=self.root.on_drop_file)
        Window.bind(on_drop_text=self.root.on_drop_text)
        return self.root

    def on_stop(self):
        self.server.quit()
        Logger.info('ndrop: quit')

    def on_pause(self):
        return True

    def on_add_node(self, node):
        self.root.dispatch('on_ndrop_event', {
            'action': 'add_node',
            'node': node,
        })

    def on_remove_node(self, node):
        self.root.dispatch('on_ndrop_event', {
            'action': 'remove_node',
            'node': node
        })

    def on_recv_text(self, text, from_addr):
        self.root.dispatch('on_ndrop_event', {
            'action': 'recv_text',
            'text': text,
            'from_addr': from_addr
        })

    def start_ndrop_server(self):
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

    def ask_runtime_permission(self, permission):
        """
        WRITE_EXTERNAL_STORAGE
        READ_EXTERNAL_STORAGE,
        MANAGE_EXTERNAL_STORAGE,
        INTERNET,
        ACCESS_NETWORK_STATE,
        ACCESS_WIFI_STATE,
        """
        if not kivy_platform == 'android':
            return
        from android.permissions import check_permission, request_permissions, Permission
        android_permission = getattr(Permission, permission)
        if not check_permission(android_permission):
            request_permissions([android_permission])
            if not check_permission(android_permission):
                Logger.warn(f'Permission: Failed to request {permission}')


def run():
    Logger.info(f'Ndrop: {about.banner}')
    if kivy_platform == 'android':
        from android.storage import app_storage_path, primary_external_storage_path
        cfg_path = app_storage_path()
        cfg_file = os.path.join(cfg_path, 'ndrop.ini')
        cfg_file = None
        init_config(cfg_file)
        gConfig.app['target_dir'] = os.path.join(primary_external_storage_path(), 'Download')
        Window.minimum_width, Window.minimum_height = 320, 360
        Window.fullscreen = True
    else:
        init_config()
        Window.fullscreen = False
        Window.minimum_width, Window.minimum_height = 320, 360
        Window.size = (320, 360)
    Logger.info(f'Kivy: Platform: {kivy_platform}')
    Logger.info(f'Config file: {gConfig.__cfg_path}')
    Logger.info(f'Target dir: {gConfig.app["target_dir"]}')

    default_font = Config.get('kivy', 'default_font').strip()
    Logger.info(f'Font: {default_font}')
    if Config.has_option('kivy', 'default_font_orig'):
        default_font_orig = Config.get('kivy', 'default_font_orig').strip()
    else:
        default_font_orig = default_font
        Config.set('kivy', 'default_font_orig', default_font_orig)
        Config.write()
    if kivy_platform == 'android':
        cjk_font = 'NotoSansCJK-Regular.ttc'
        resource_add_path(r'/system/fonts')
    elif kivy_platform == 'win':
        cjk_font = 'msyh.ttc'
        resource_add_path(r'C:\Windows\Fonts')
    elif kivy_platform == 'linux':
        resource_add_path(r'/usr/share/fonts/truetype/droid')
        cjk_font = 'DroidSansFallbackFull.ttf'
    else:
        cjk_font = None
    if cjk_font and cjk_font not in default_font:
        cjk_font_path = resource_find(cjk_font)
        # Kivy font: ['Roboto', 'data/fonts/Roboto-Regular.ttf', 'data/fonts/Roboto-Italic.ttf', 'data/fonts/Roboto-Bold.ttf', 'data/fonts/Roboto-BoldItalic.ttf']
        # kivy/core/text/__init__.py register(name, fn_regular, fn_italic=None, fn_bold=None, fn_bolditalic=None):
        if cjk_font_path:
            fonts = [f.strip("' ") for f in default_font_orig.strip('[]').split(',')]
            fonts[1] = cjk_font_path
            Config.set('kivy', 'default_font', str(fonts))
            Config.write()
            Logger.info(f'Fix Font: {fonts}')

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
