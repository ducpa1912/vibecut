"""DuckSuite local core.

The Mac shell starts this process, passes a per-launch token on stdin, and reads
one JSON handshake line from stdout. Nothing here is reachable from the network:
the server binds 127.0.0.1 only.
"""

__version__ = "1.0.0"
