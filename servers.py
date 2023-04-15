import os
import sys
from types import ModuleType
from pathlib import Path

from .transporters import *
from .proxy import *
from .connection import *

from .base import BaseHandler

scripts_path = os.path.join(Path(__file__).parent.absolute(), "scripts")


class VirtualModule(ModuleType):

    def __init__(self, server, *a, **kw):
        self.__server = server
        super().__init__(*a, **kw)

    def __getattr__(self, name):
        if not name.startswith('__'):
            return self.__server.import_lib(name)
        raise AttributeError


class VirtualModuleMain(ModuleType):

    def __init__(self, server, *a, **kw):
        self.__server = server
        super().__init__(*a, **kw)

    def __getattr__(self, name):
        if not name.startswith('__'):
            return getattr(self.__server, name)
        raise AttributeError


class VirtualModuleImportRedirect(object):
    def __init__(self, name, server):
        ''' Create a virtual package that redirects imports (see PEP 302). '''
        self.name = name
        self.server = server
        self.module = VirtualModule(self.server, name)

        sys.modules.setdefault(
            name, self.module
        )
        self.module.__dict__.update(
            {
                '__file__': __file__,
                '__path__': [],
                '__all__': [],
                '__loader__': self
            }
        )
        sys.meta_path.append(self)

    def find_module(self, fullname, path=None):
        if '.' not in fullname:
            return
        packname = fullname.rsplit('.', 1)[0]
        if packname != self.name:
            return
        return self

    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]
        # modname = fullname.rsplit('.', 1)[1]
        # realname = self.impmask % modname
        # __import__(realname)

        names = fullname.split(".")[1:]
        modname = "/".join(names)

        # for i, name in enumerate(names):
        #     sys.modules[".".join(names[:i])] = self.module

        module = VirtualModuleMain(getattr(self.module, modname), fullname.split(".")[-1])
        sys.modules[fullname] = module

        # module = sys.modules[fullname]  # = sys.modules[realname]
        # setattr(self.module, modname, module)
        # module.__loader__ = self
        return module


class BaseBridgeServer(BaseHandler):
    args = []
    import_alias = 'bridge'
    default_transporter = SocketBridgeTransporter

    def __init__(self, transporter=None, keep_alive=False, timeout=5):
        self.transporter = transporter

        if not self.transporter:
            self.transporter = self.default_transporter()

        self.timeout = timeout

        self.__keep_alive = keep_alive

        super().__init__()
        self.formatters = {
            # "number": lambda x: int(x['value']),
            # "float": lambda x: float(x['value']),
            # "string": lambda x: str(x['value']),
            # "array": lambda x: list(x['value']),
            # "Buffer": lambda x: bytes(x['data']),
            # "object": lambda x: dict(x),
            # "set": lambda x: set(x['value']),
            # "boolean": lambda x: bool(x['value']),
            # "callable_proxy": self.callable_proxy,
            # "function": self.callable_proxy,
            # "bridge_proxy": lambda x: self.getProxyObject(x['value'])
        }

    def setup_imports(self, name):
        # class BridgeModule(ModuleType):
        #     def __getattr__(self, name):
        #         if not name.startswith('__'):
        #             return _self.conn.require(name)
        #         raise AttributeError

        # sys.modules[name] = VirtualModule(self, name)
        # sys.meta_path.append(VirtualModuleFinder(self, name))
        VirtualModuleImportRedirect(name, self)

    def import_lib(self, name):
        return

    def setup(self, *a, name=None, **k):
        conn = self.start(*a, **k)
        self.setup_imports(name or self.import_alias)
        return conn

    def start(self, bridge=None, mode="auto_eval"):
        self.bridge = bridge
        self.conn = self.create_connection(mode=mode)
        self.transporter.start(
            on_message=self.on_message,
            server=self
        )
        return self.conn

    def create_connection(self, mode):
        return self.connection(
            transporter=self.transporter,
            bridge=self.bridge, mode=mode,
            server=self
        )

    def on_message(self, message):
        # print("[PY] putting in queue:", message)
        if isinstance(message, dict):
            if 'action' in message:
                # s = getattr(self, "socket", None)
                # print("Processing:", message, self, "\n")
                # if s:print(s, self.transporter.MAP, s.handler.rfile, self.proxies, "\n\n")

                response = self.process_command(message)
                response['message_id'] = message['message_id']
                # print("RES:", response)
                return self.send(**response)
            elif message.get('error'):
                return self.queue.put_nowait(
                    Exception(message['error'])
                )
            else:
                handler = self.message_handlers.get(message.get("message_id"))

                if handler:
                    return handler(message)
                else:
                    if message.get("response", UNDEFINED) != UNDEFINED:
                        message = message['response']
                    elif message.get("value", UNDEFINED) != UNDEFINED:
                        message = message['value']

                    return self.queue.put_nowait(message)
        return self.queue.put_nowait(message)
    
    def __enter__(self):
        return self
    
    def __exit__(self, *a):
        self.stop()

    def __keep_alive__(self):
        self.__keep_alive = True

    def stop(self, force=False):
        if not force and self.__keep_alive:
            return
        self.transporter.stop()
        # self.bridge.close()

    def __del__(self):
        self.stop()


class NodeBridgeServer(BaseBridgeServer):
    proxy = NodeBridgeProxy
    connection = NodeBridgeConnection

    args = ["node", os.path.join(scripts_path, "js_bridge_script.js")]
    import_alias = 'nodejs'

    def import_lib(self, name):
        if name == "global":
            return self.conn

        old, self.timeout = self.timeout, 2
        name = self.__format_name__(name)
        try:
            ret = self.conn.require(name)
        except Exception:
            try:
                ret = getattr(self.conn, name)
            except Exception:
                raise ImportError(f"Unable to resolve import '{name}'")
        self.timeout = old
        return ret

    def __format_name__(self, name):
        return name.replace("__", "-")

    def proxymise(self, item):
        setattr(item, "__node_bridge_proximise__", True)
        return item

    def generate_proxy(self, arg):
        ret = super().generate_proxy(arg)
        ret['proxymise'] = getattr(arg, "__node_bridge_proximise__", False)
        return ret


def nodejs(host='127.0.0.1', port=7000, **kw):
    return NodeBridgeServer(
        SocketBridgeTransporter(host, port), **kw
    ).setup()


class BrowserBridgeServer(NodeBridgeServer):
    default_transporter = WebSocketBridgeTransporter
    import_alias = "browser"

    def import_lib(self, name):
        if name == "conn":
            return self.conn

        old, self.timeout = self.timeout, 5
        name = self.__format_name__(name)
        try:
            ret = getattr(self.conn, name)
        except Exception:
            raise ImportError(f"Unable to resolve import '{name}'")
        self.timeout = old
        return ret

class JSBridgeServer(JSBridgeTransporter):
    pass

class BrowserBridgeHandler(BrowserBridgeServer):
    connection = BrowserBridgeConnection

    def __init__(self, socket, rfile, *a, **kw):
        self.socket = socket
        self.bridge = None
        self.rfile = rfile
        super().__init__(*a, **kw)

    def send(self, raw=False, **data):
        self.transporter.send(self.rfile, data, raw)

    def __exit__(self, *a):
        pass

def browser(host='127.0.0.1', port=7001, **kw):
    return BrowserBridgeServer(
        WebSocketBridgeTransporter(host, port), **kw
    ).setup()


class RubyBridgeServer(BaseBridgeServer):
    proxy = RubyBridgeProxy
    connection = RubyBridgeConnection

    import_alias = 'ruby'


class JavaBridgeServer(BaseBridgeServer):
    proxy = JavaBridgeProxy
    connection = JavaBridgeConnection

    import_alias = 'java'


class CSharpBridgeServer(BaseBridgeServer):
    proxy = CSharpBridgeProxy
    connection = CSharpBridgeConnection

    import_alias = 'csharp'


class GoLangBridgeServer(BaseBridgeServer):
    proxy = GoLangBridgeProxy
    connection = GoLangBridgeConnection

    import_alias = 'golang'


"python -m py_bridge --client --mode=std"
"python -m py_bridge --client --mode=websocket --host=127.0.0.1:8080"

"npx js_bridge --client --mode=std"
"npx js_bridge --client --mode=websocket --host=127.0.0.1:8080"
