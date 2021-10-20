
name = 'ndrop'
version = '1.5.11'
author = 'Yugang LIU'
email = 'liuyug@gmail.com'
url = 'https://github.com/liuyug/ndrop.git'
license = 'MIT'
description = 'File Transfer Tool.'
detail = 'Compatible "Dukto" and "NitroShare". support "HTTP File Server (HFS)"'

banner = '%s v%s - %s' % (name.capitalize(), version, description)
about = '%s v%s - written by %s <%s>' % (name.capitalize(), version, author, email)


def get_system_symbol(system):
    symbols = {
        'linux': 'Linux',
        'darwin': 'Apple',
        'windows': 'Windows',
        'android': 'Android',
    }
    return symbols.get(system.lower(), system)
