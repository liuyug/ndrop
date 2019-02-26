=====
NDrop
=====
a File Transfer Tool. compatible "Dukto_" and "NitroShare_"

Feature
=======
+   Just drop. No authentication, no authorize, use in trusted network.
+   compatible "Dukto_" and "NitroShare_"
+   only CLI mode, no GUI. Dukto_ or NitroShare_ all provide GUI window.
+   transfer File, Directory. Dukto_ also send TEXT
+   output to DISK or STDOUT

Install
=======

.. code::

    # from pypi
    pip3 install ndrop

    # from source code
    python3 setup.py install

Using Scenarios
===============
Client to Server
----------------
on Server(ndrop or Dukto_)::

    $ ndrop --listen 0.0.0.0 /tmp
    My Node: user at DESKTOP-client (Linux)
    [Dukto] listen on 0.0.0.0:4644 - [127.0.0.1,192.168.0.1]
    [NitroShare] listen on 0.0.0.0:40818 - [127.0.0.1,192.168.0.1]
    Online : [Dukto] 192.168.0.10:4644 - User at DESKTOP-LU1OA8H (Windows)
    Online : [NitroShare] 192.168.0.11:40818 - USER-4VC7CASHSL (windows)
    [process bar ... ]

or output to STDOUT or PIPE::

    $ ndrop --listen 0.0.0.0 - | mpv -

on Client(ndrop, Dukto_ or NitroShare_)::

    $ ndrop --mode dukto --send 192.168.0.1 /tmp/100M.bin
    # or
    $ ndrop --mode nitroshare --send 192.168.0.1 /tmp/100M.bin
    [process bar ... ]

Client to Server with SSL
-------------------------
Maybe transfer though PUBLIC network, such as Internet. Dukto_ do not support SSL.

on Server::

    $ ndrop ~/cert.pem --key ~/key.pem --listen 0.0.0.0 /tmp
    My Node: user at DESKTOP-client (Linux)
    [Dukto] listen on 0.0.0.0:4644 - [127.0.0.1,192.168.0.1]
    [NitroShare] listen on 0.0.0.0:40818 - [127.0.0.1,192.168.0.1]
    Online : [Dukto] 192.168.0.10:4644 - User at DESKTOP-LU1OA8H (Windows)
    Online : [NitroShare] 192.168.0.11:40818 - USER-4VC7CASHSL (windows)
    [process bar ... ]

on Client::

    $ ndrop --mode dukto ~/cert.pem --key ~/key.pem --send 192.168.0.1 /tmp/100M.bin
    [process bar ... ]


.. _Dukto: https://sourceforge.net/projects/dukto/
.. _NitroShare: https://nitroshare.net/
