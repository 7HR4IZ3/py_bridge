import queue
from weakref import WeakKeyDictionary
from .servers import *


class PyBridge:
    def __init__(self):
        self.queue = queue.Queue()
        self.proxies = WeakKeyDictionary()

    def connect(self, server: BaseBridgeServer, mode="auto_eval"):
        self.server = server
        return self.server.start(self, mode)

    def close(self):
        pass
