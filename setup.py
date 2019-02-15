
from setuptools import setup, find_packages

from netdrop import about

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
    name='ndrop',
    version=about.version,
    author_email='liuyug@gmail.com',
    url='https://github.com/liuyug/ndrop.git',
    license='GPLv3',
    description='a File Transfer Tool. Support "Dukto"',
    long_description=long_description,
    python_requires='>=3',
    platforms=['noarch'],
    packages=find_packages(exclude=['doc']),
    entry_points={
        'console_scripts': [
            'ndrop = netdrop.main:run',
        ],
    },
    install_requires=requirements,
    zip_safe=False,
)
