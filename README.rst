=====
NDrop
=====
a File Transfer Tool. compatible "Dukto_"

Feature
=======
+   Just drop. No authentication, no authorize, use in trusted network.
+   compatible "Dukto_"
+   only CLI mode, no GUI. Dukto_ provide GUI window.
+   transfer File, Directory and TEXT
+   output to DISK or STDOUT

Install
=======

.. code::

    # from pypi
    pip3 install ndrop

    # from source code
    python3 setup.py install

Using Scenario
===============
Client to Server
----------------
on Server(ndrop or Dukto_)::

    $ ndrop --listen 0.0.0.0 /tmp
    My Signature: user at DESKTOP-client (Linux)
    listen on 0.0.0.0:4644 - [127.0.0.1,192.168.0.1]
    [process bar ... ]

or output to STDOUT or PIPE::

    $ ndrop --listen 0.0.0.0 - | mpv -

on Client(ndrop or Dukto_)::

    $ ndrop --send 192.168.0.1 /tmp/100M.bin
    [process bar ... ]

Client to Server with SSL
-------------------------
Maybe transfer though PUBLIC network, such as Internet. Dukto_ do not support SSL.

on Server::

    $ ndrop ~/cert.pem --key ~/key.pem --listen 0.0.0.0 /tmp
    My Signature: user at DESKTOP-client (Linux)
    listen on 0.0.0.0:4644 - [127.0.0.1,192.168.0.1]
    [process bar ... ]

on Client::

    $ ndrop ~/cert.pem --key ~/key.pem --send 192.168.0.1 /tmp/100M.bin
    [process bar ... ]


.. _Dukto: https://sourceforge.net/projects/dukto/
