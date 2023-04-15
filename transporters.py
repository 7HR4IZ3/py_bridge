import json
import os
import socket
import termcolor
import threading
import gevent
import select
import asyncio
import queue
import time
from tempfile import NamedTemporaryFile
from subprocess import Popen

from .utils import task, process, daemon_task


try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()

try:
    import websockets
except ImportError:
    websockets = None


class BaseBridgeTransporter:
    listening = True

    def setup(self):
        return

    def get_setup_args(self, args, **kwargs):
        return args

    def start(self, on_message, server):
        self.on_message = on_message
        self.server = server
        self.setup()

    def start_client(self):
        pass

    def encode(self, data, raw=False):
        return (
            json.dumps(data) if raw
            else json.dumps(data, cls=self.server.encoder)
        )

    def decode(self, data, raw=False):
        return (
            json.loads(data) if raw
            else json.loads(data, cls=self.server.decoder)
        )

    def send(self, data):
        pass

    def stop(self):
        pass


class ProcessBasedTransporter(BaseBridgeTransporter):

    @task
    def start_process(self, server):
        # print(os.getcwd())
        args, kwargs = self.get_setup_args(server.args)
        self.process = Popen(args, cwd=os.getcwd(), **kwargs)

    def stop_process(self):
        self.process.terminate()

    def start(self, on_message, server):
        self.start_process(server)
        super().start(on_message, server)

    def stop(self):
        self.stop_process()


class StdIOBridgeTransporter(ProcessBasedTransporter):

    def get_setup_args(self, args, **kwargs):
        self.stdin = NamedTemporaryFile(delete=False)
        self.stdout = NamedTemporaryFile(delete=False)

        # return args + [
        #     "--mode", "stdio",
        #     "--stdin", self.stdout.name,
        #     "--stdout", self.stdin.name
        # ], {}
        return args + [
            self.stdout.name,
            self.stdin.name
        ], {}

    def setup(self):
        super().setup()
        self.listening = True
        self.start_listening()

    def send(self, data):
        data = self.encode(data).encode("utf-8")

        self.stdout.seek(0)
        self.stdout.write(data)
        self.stdout.seek(0)

        # print("[Py] Sent", data)r
        # time.sleep(0.19)
        # self.stdout.truncate()
        # self.stdout.seek(0)

    @task
    def start_listening(self, mode="listening"):
        if mode == "listening":
            target = self.stdin
        else:
            target = self.stdout

        while self.process.poll() is None:
            target.seek(0)
            data = str(target.read(), "utf-8")

            if not data:
                continue

            # print("[PY] Recieved:", data)
            self.on_message(self.decode(data))
            target.seek(0)
            target.truncate()
            # self.stdout.seek(0)
            # self.stdout.truncate()

    def __del__(self):
        self.listening = False


class SocketBridgeTransporter(ProcessBasedTransporter):

    def __init__(self, host='127.0.0.1', port=7000):
        self.host = host
        self.port = port
        self.socket = None
        self.tasks = []

    def get_setup_args(self, args, **kw):
        return args + [
            self.host,
            str(self.port),
            'socket'
        ], {}

    def start_listening(self, cond):
        while cond() is None:
            try:
                data = self.socket.recv(1024)
            except Exception:
                break

            if data == b"":
                break

            if data:
                data = data.decode("utf-8")
                # print("[PY] Recieved:", data)
                # termcolor.cprint(f"[PY -> JS] Recieved: {data}", color="green")
                for item in data.split("\n"):
                    item = item.strip()
                    if item:
                        self.on_message(self.decode(item))

    def send(self, data, raw=False):
        data["response_type"] = "bridge_response"

        data = self.encode(data, raw)
        # print("[Py] Sent", data)
        # termcolor.cprint(f"[PY -> JS] Sent: {data}", color="red")
        if self.socket:
            sent = self.socket.send(data.encode('utf-8') + b"\n")
            if sent == 0:
                pass
        else:
            self.tasks.append(data)

    def setup(self):
        super().setup()
        addr = (self.host, self.port)
        if False:  # socket.has_dualstack_ipv6():
            # create an INET, STREAMing socket
            self.sock_server = socket.socket(
                socket.AF_INET6, socket.SOCK_STREAM
            )
        else:
            self.sock_server = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            )
        # bind the socket to a public host, and a well-known port
        # print("Binding to:", addr)
        self.sock_server.bind(addr)
        # become a server socket
        self.sock_server.listen()

        return self.handle_connection()

    def handle_connection(self):
        self.socket, _ = self.sock_server.accept()

        for item in self.tasks:
            self.send(item)

        task(self.start_listening)(lambda: self.process.poll())

    def start_client(self, on_message, options=None, server=None, queue=None):
        options = options or {}
        self.on_message = on_message
        self.queue = queue
        self.server = server
        self.host = options.get("host", "localhost")
        self.port = options.get("port", 7000)

        addr = (self.host, self.port)

        self.socket = socket.socket(
            socket.AF_INET6, socket.SOCK_STREAM
        )
        self.socket.connect(addr)

        self.start_listening(lambda: None)


class JSBridgeTransporter(BaseBridgeTransporter):

    def __init__(self, host='127.0.0.1', port=7001, timeout=5, setup=True):
        self.host = host
        self.port = port
        self.socket = None
        self.listening = threading.Event()
        self.listening.set()
        self.tasks = []
        self.last_socket = None
        self.started_listening = False
        self.timeout = timeout
        self.connQ = queue.Queue()
        self.CONNECTION_LIST = []
        self.MAP = {}
        self.SOCKET_MAP = {}

        if setup: self.setup()

    def encode(self, target, data, raw=False):
        return (
            json.dumps(data) if raw
            else json.dumps(data, cls=target.encoder)
        )

    def decode(self, target, data, raw=False):
        return (
            json.loads(data) if raw
            else json.loads(data, cls=target.decoder)
        )

    def get_setup_args(self, args, **kw):
        return args, kw

    @task
    def start_listening(self):
        self.started_listening = True
        while self.listening.is_set():
            if not self.CONNECTION_LIST:
                continue
            try:
                sockets, _, _ = select.select(self.CONNECTION_LIST, [], [], 2)
            except Exception:
                continue

            for sock in sockets:
                target = self.MAP[sock]
                try:
                    data = target.socket.receive()
                except Exception:
                    self.listening.clear()
                    break

                if data:
                    # data = data.decode("utf-8")
                    for item in data.split("\n"):
                        item = item.strip()
                        # print("[PY] Recieved:", item)
                        if item:
                            (target.on_message)(self.decode(target, item))

    # def send(self, data, raw=False):
    #     global loop
    #     data = self.encode(data, raw).encode('utf-8')
    #     print("[Py] To Send", data)
    #     if self.socket:
    #         try:
    #             async def main():
    #                 print("[Py] Sent", data)
    #                 self.socket.send(data + b"\n")

    #             if not loop:
    #                 try:
    #                     loop = asyncio.get_event_loop()
    #                 except RuntimeError:
    #                     loop = None

    #             if loop:
    #                 loop.run_until_complete(main())
    #                 loop.run_forever()
    #             else:
    #                 asyncio.run(main())
    #         except Exception:
    #             self.listening = False
    #     else:
    #         self.tasks.append(data)

    def send(self, rfile, data, raw=False):
        if rfile:
            target = self.MAP[rfile]
            # print("[Py] To Send:", data)
            data = self.encode(target, data, raw).encode('utf-8')
            # print("[Py] Sent:", data)
            try:
                target.socket.send(data + b"\n")
            except Exception as e:
                print("Error:", repr(e))
                self.listening.clear()
        else:
            self.tasks.append(data)

    @daemon_task
    def setup_app(self):
        from gevent import pywsgi
        from geventwebsocket.handler import WebSocketHandler

        def websocket_app(environ, start_response):
            socket = environ["wsgi.websocket"]
            self.handle_connection(socket)
            return []

        server = pywsgi.WSGIServer(
            (self.host, self.port), websocket_app,
            handler_class=WebSocketHandler
        )
        # print("Starting ws server:", f"host: {self.host}, port: {self.port}")
        server.serve_forever()

    def setup(self):
        self.setup_app()
        # def _():
        #     self.connQ.get()
        #     self.start_listening()
        # task(_)()

    def handle_connection(self, socket):
        from .servers import BrowserBridgeHandler
        rfile = socket.handler.rfile
        try:
            # print("New:", socket)
            self.CONNECTION_LIST.append(rfile)

            handler = BrowserBridgeHandler(socket, rfile, transporter=self)
            handler.conn = handler.create_connection(mode="auto_eval")

            self.MAP[rfile] = handler
            self.connQ.put(handler.conn)

            while True:
                try:
                    data = socket.receive()
                except Exception:
                    self.listening.clear()
                    break

                if data:
                    # data = data.decode("utf-8")
                    for item in data.split("\n"):
                        item = item.strip()
                        # print("[PY] Recieved:", item)
                        if item:
                            daemon_task(handler.on_message)(self.decode(handler, item))
            # print("Quiting")
            return []
        finally:
            try:
                self.CONNECTION_LIST.remove(rfile)
                h = self.MAP.pop(rfile)
                del h
            except:pass

    def get_connection(self, func=None, *a, **kw):

        def _():
            try:
                conn = self.connQ.get(self.timeout)
                self.connQ.task_done()
                if conn:
                    if func:
                        func(conn, *a, **kw)
                    else:
                        return conn
            except queue.Empty:
                pass
            return None
        
        if func:
            return daemon_task(_)()
        else:
            return _()

    def close(self):
        self.listening.clear()

    # def __del__(self):
    #     self.close()

class WebSocketBridgeTransporter(BaseBridgeTransporter):
    pass

class SocketIOBridgeTransporter(BaseBridgeTransporter):

    def __init__(self, host='127.0.0.1', port=7001):
        self.host = host
        self.port = port
        self.socket = None
        self.listening = threading.Event()
        self.listening.set()
        self.tasks = []

    def get_setup_args(self, args, **kw):
        return args, kw

    def send(self, data, raw=False):
        data = self.encode(data, raw).encode('utf-8')
        # print("[Py] Sent", data)
        if self.socket:
            try:
                self.socket.emit("message", data + b"\n")
            except Exception:
                self.listening = False
        else:
            self.tasks.append(data)

    @task
    def setup_app(self):
        from socketio import Server, WSGIApp
        from gevent import pywsgi
        # from geventwebsocket.handler import WebSocketHandler

        io = Server(async_mode="gevent")
        self.socket = io

        app = WSGIApp(io, socketio_path="")

        @io.event
        def message(ev, data):
            # print(data)
            if data:
                for item in data.split("\n"):
                    item = item.strip()
                    if item:
                        self.on_message(self.decode(item))

        for item in self.tasks:
            self.socket.emit("message", item)

        server = pywsgi.WSGIServer(
            (self.host, self.port), app
            # handler_class=WebSocketHandler
        )
        # print("Starting ws server:", f"host: {self.host}, port: {self.port}")
        server.serve_forever()

    def setup(self):
        self.setup_app()

    def start_client(self, on_message, options=None, server=None):
        options = options or {}
        self.on_message = on_message
        self.server = server
        self.host = options.get("host", "localhost")
        self.port = options.get("port", 7000)

        self.setup_app()

    def __del__(self):
        self.listening.clear()


transporters = {
    "stdio": StdIOBridgeTransporter,
    "socket": SocketBridgeTransporter,
    "websocket": WebSocketBridgeTransporter,
    "socketio": SocketIOBridgeTransporter
}
