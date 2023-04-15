import json
import sys
import asyncio
from threading import Thread
from multiprocessing import Process
from functools import wraps
from random import randint

from .proxy import BaseBridgeProxy


def run_safe(func, *args, **kwargs):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    return loop.call_soon(func, *args, **kwargs)


def task(func, handler=Thread, *ta, **tkw):
    @wraps(func)
    def wrapper(*a, **kw):
        thread = handler(*ta, target=func, args=a, kwargs=kw, **tkw)
        thread.start()
        return thread
    return wrapper


def daemon_task(func):
    return task(func, handler=Thread, daemon=True)


def process(func):
    return task(func, handler=Process)

class JsClass:
    def __serialize_bridge__(self, server):
        return self.__dict__

def get_encoder(server):
    class JSONEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, BaseBridgeProxy):
                return {
                    'type': 'bridge_proxy',
                    'location': obj.__data__['location'],
                    'reverse': True
                }
            if isinstance(obj, tuple):
                return server.generate_proxy(obj)

            if isinstance(obj, JsClass):
                obj = obj.__dict__
                return json.dumps(obj, cls=JSONEncoder)
            
            try:
                if issubclass(obj, JsClass):
                    obj = obj.__dict__
                    print("JsClass", obj)
                    return json.dumps(obj, cls=JSONEncoder)
            except: pass

            if hasattr(obj, "__serialize_bridge__"):
                obj = obj.__serialize_bridge__(server)

            try:
                return super().encode(obj)
            except:
                return server.generate_proxy(obj)
    return JSONEncoder


def get_decoder(server):
    class JSONDecoder(json.JSONDecoder):
        def __init__(self, *a, **kw):
            super().__init__(object_hook=self.object_hook, *a, **kw)

        def object_hook(self, item: dict):
            for key, val in item.items():
                if isinstance(val, list):
                    vall = [
                        self.object_hook(x) if isinstance(x, dict) else x
                        for x in val
                    ]
                    item[key] = vall

            # if item.get("type") == "bridge_proxy" and item.get("location"):
            #     return server.proxy(server, item)
            return server.get_result(item)
    return JSONDecoder

def makeProxyClass(target):
    class JsClass(object):
        def __init__(self, *a, **kw):
            self.__object = self.proxy.new(*a, **kw)

        def __getattr__(self, name):
            return self.__object.__getattr__(name)

        def __call__(self, *a, **kw):
            return self.__object.__call__(*a, **kw)

def load_module(target, e=None, catch_errors=True, **namespace):
    try:
        if ':' in target:
            module, target = target.split(":", 1)
        else:
            module, target = (target, None)
        if module not in sys.modules:
            __import__(module)
        if not target:
            return sys.modules[module]
        if target.isalnum():
            return getattr(sys.modules[module], target)
        package_name = module.split('.')[0]
        namespace[package_name] = sys.modules[package_name]
        return eval('%s.%s' % (module, target), namespace)
    except Exception as err:
        if catch_errors:
            return e
        raise err


def generate_random_id(size=20):
    return "".join([str(randint(0, 9)) for i in range(size)])
