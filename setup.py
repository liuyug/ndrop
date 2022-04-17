
from setuptools import setup, find_packages

from ndrop import about

with open('README.rst') as f:
    long_description = f.read()

requirements = []
with open('requirements.txt') as f:
    for line in f.readlines():
        line.strip()
        if line.startswith('#'):
            continue
        requirements.append(line)

setup(
    name=about.name,
    version=about.version,
    author_email=about.email,
    url=about.url,
    license=about.license,
    description=about.description,
    long_description=long_description,
    python_requires='>=3.6',
    platforms=['noarch'],
    packages=['ndrop', 'tkinterdnd2'],
    package_data={
        'ndrop': [
            'image/*.*',
        ],
        'tkinterdnd2': [
            'tkdnd/linux64/*.*',
            'tkdnd/osx64/*.*',
            'tkdnd/win64/*.*',
        ]
    },
    entry_points={
        'console_scripts': [
            '%s = ndrop.__main__:run' % about.name,
        ],
        'gui_scripts': [
            '%stk = ndrop.__main_tk__:run' % about.name,
            '%skivy = ndrop.__main_kivy__:run' % about.name,
        ],
    },
    install_requires=requirements,
    zip_safe=False,
)
