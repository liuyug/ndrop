import os
from configparser import ConfigParser

from platformdirs import PlatformDirs


def singleton(cls):
    instances = {}

    def getinstance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return getinstance


@singleton
class gConfig():
    pass


def init_config(cfg_path=None):
    config = ConfigParser()

    dirs = PlatformDirs('ndrop', '')
    if True:
        appname = 'ndrop'
        appauthor = ''
        print('user_data_dir:', dirs.user_data_dir(appname, appauthor))
        print('user_cache_dir:', dirs.user_cache_dir(appname, appauthor))
        print('user_log_dir:', dirs.user_log_dir(appname, appauthor))
        print('user_config_dir:', dirs.user_config_dir(appname))
        print('user_documents_dir:', dirs.user_documents_dir())
        print('user_runtime_dir:', dirs.user_runtime_dir(appname, appauthor))

    if not cfg_path:
        cfg_path = os.path.join(dirs.user_config_dir, 'ndrop.ini')
    gConfig.config_path = cfg_path

    gConfig.config_path = cfg_path
    if not os.path.exists(cfg_path):
        target_dir = dirs.user_documents_dir
        cfg_text = f"""[app]
target_dir = {target_dir}
enable_hdpi = False
create_node_by_text = True
"""
        dir_name = os.path.dirname(cfg_path)
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
        with open(cfg_path, 'wt', encoding='utf-8') as f:
            f.write(cfg_text)

    config.read(cfg_path, encoding='utf-8')
    for section in config.sections():
        setattr(gConfig, section, {})
        for k, v in config.items(section):
            getattr(gConfig, section)[k] = v
    gConfig.app['enable_hdpi'] = gConfig.app.get('enable_hdpi') == 'True'
    gConfig.app['create_node_by_text'] = gConfig.app.get('create_node_by_text') == 'True'


def save_config(cfg_path=None):
    if not cfg_path:
        cfg_path = gConfig.config_path
    config = ConfigParser()
    for item in dir(gConfig):
        if item.startswith('__'):
            continue
        if item == 'config_path':
            continue
        value = getattr(gConfig, item)
        config[item] = value

    dir_name = os.path.dirname(cfg_path)
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)
    with open(cfg_path, 'wt', encoding='utf-8') as configfile:
        config.write(configfile)
