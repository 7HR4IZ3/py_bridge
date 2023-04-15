import os
import builtins
import queue

from types import NoneType
from pathlib import Path
from functools import partial
from threading import Thread, current_thread

from .transporters import *
from .proxy import *
from .connection import *

from .utils import generate_random_id, get_decoder, get_encoder

scripts_path = os.path.join(Path(__file__).parent.absolute(), "scripts")


class BaseHandler:
    proxy = BaseBridgeProxy
    connection = BaseBridgeConnection

    default_transporter = StdIOBridgeTransporter

    def __init__(self):
        self.proxies = dict()

        self.queue = queue.Queue()
        self.timeout = 5

        self.message_handlers = dict()

        self.encoder = get_encoder(self)
        self.decoder = get_decoder(self)

        self.formatters = {
            "number": lambda x: int(x['value']),
            "float": lambda x: float(x['value']),
            "string": lambda x: str(x['value']),
            "array": lambda x: list(x['value']),
            "Buffer": lambda x: bytes(x['data']),
            "object": lambda x: dict(x),
            "set": lambda x: set(x['value']),
            "boolean": lambda x: bool(x['value']),
            "callable_proxy": self.callable_proxy,
            "function": self.callable_proxy,
            # "bridge_proxy": lambda x: self.getProxyObject(x['value'])
        }

    def random_id(self, size=20):
        return generate_random_id(size)

    def proxy_object(self, arg):
        for k, v in self.proxies.items():
            try:
                if v == arg:
                    return k
            except Exception:
                continue

        key = generate_random_id()
        self.proxies[key] = arg
        return key

    def generate_proxy(self, arg):
        key = self.proxy_object(arg)

        t = str(type(arg).__name__)
        if t in ["function", "method", "lambda"]:
            t = "callable_proxy"

        return {
            "type": "bridge_proxy",
            "obj_type": t,
            "location": key
        }

    def get_proxy(self, key):
        return self.proxies.get(key)

    def callable_proxy(self, target):
        def wrapper(*args, **kwargs):
            return self.recieve(
                action="call_proxy",
                location=target['location'],
                args=args,
                kwargs=kwargs
            )
        return wrapper

    def format_arg(self, arg):
        ret = []

        # elif isinstance(arg, JsObject):
        #     ret.append(arg.code)
        if isinstance(arg, BridgeChain):
            ret.append(arg._statement())
        elif isinstance(arg, BaseBridgeProxy):
            ret.append(f"client.get_proxy_object('{arg.__data['location']}')")
        # elif isinstance(arg, JsClass):
        #     item = self.state.proxy_object(arg)
        #     ret.append("client.__get_result("+item+")")
        elif isinstance(arg, list):
            ret.append("[")
            [ret.append(x) for x in self.format_args(arg)]
            ret.append("]")
        elif isinstance(arg, tuple):
            ret.append("(")
            [ret.append(x) for x in self.format_args(arg)]
            ret.append(")")
        elif isinstance(arg, set):
            ret.append("{")
            [ret.append(x) for x in self.format_args(arg)]
            ret.append("}")
        elif isinstance(arg, dict):
            ret.append("{")
            for k, v in arg.items():
                [ret.append(x) for x in self.format_arg(k)]
                ret.append(":")
                [ret.append(x) for x in self.format_arg(v)]
                ret.append(",")
            if len(ret) > 1 and ret[-1] == ",":
                ret.pop()
            ret.append("}")
        # elif hasattr(arg, "to_js"):
        #     [ret.append(x) for x in arg.to_js(self, arg)]
        elif arg is None:
            ret.append("null")
        else:
            if not isinstance(arg, (int, str, dict, set, tuple, bool, float)):
                item = self.generate_proxy(arg)
                ret.append("client.generate_proxy(" + item + ")")
            else:
                val = repr(arg)
                ret.append(f'{val}')
        return ret

    def format_args(self, args):
        ret = []

        for item in args[:-1]:
            [ret.append(x) for x in self.format_arg(item)]
            ret.append(",")

        if len(args) > 0:
            [ret.append(x) for x in self.format_arg(args[-1])]

        if ret and ret[-1] == ",":
            ret.pop()
        return ret

    def send(self, raw=False, **data):
        self.transporter.send(data, raw)

    def recieve(self, **data):
        mid = generate_random_id()
        data["message_id"] = mid

        def handler(message):
            self.message_handlers.pop(mid, None)
            # print(mid, data, message)
            try:
                if message.get("response", UNDEFINED) != UNDEFINED:
                    message = message['response']
                elif message.get("value", UNDEFINED) != UNDEFINED:
                    message = message['value']

                self.queue.put(message)
            except Exception:
                self.queue.put(message)

        self.message_handlers[mid] = handler
        self.send(**data)

        # print("Waiting for response...")

        response = self.queue.get(timeout=self.timeout)
        # print("Recieved response...")
        self.queue.task_done()
        if isinstance(response, Exception):
            raise response
        return response

    def process_command(self, req):
        func = getattr(self, "handle_" + req['action'])

        if (not func):
            raise Exception("Invalid action.")
        ret = func(req)

        return {"response": ret}

    def handle_attribute(self, req):
        target = getattr(self.obj, req["item"], UNDEFINED)
        handle = None
        if not (target is UNDEFINED):
            t = str(type(target).__name__)
            if isinstance(target, BaseBridgeProxy):
                target = target.__data__["location"]
                t = "bridge_proxy"
            elif not isinstance(
                target,
                (int, str, dict, set, tuple, bool, float, NoneType)
            ):
                handle = self.proxy_object(target)
                target = None

            if t in ["function", "method"]:
                t = "callable_proxy"
            try:
                return {"type": t, "value": target, "location": handle}
            except Exception:
                return {"type": t, "value": str(target), "location": handle}
        return {"type": None, "value": None, "error": True}

    def handle_evaluate(self, req):
        target = getattr(builtins, req["value"], UNDEFINED)
        return target

    def handle_evaluate_stack_attribute(self, req):
        stack = req["stack"]
        ret = getattr(builtins, stack[0])
        for item in stack[1:]:
            ret = getattr(ret, item)
        return ret

    def handle_get_stack_attribute(self, req):
        stack = req.get("stack") or []
        ret = self.get_proxy(req["location"])
        for item in stack:
            ret = getattr(ret, item)
        return ret

    def handle_get_stack_attributes(self, req):
        stack = req.get("stack") or []
        ret = self.get_proxy(req["location"])
        for item in stack:
            ret = getattr(ret, item)
        return dir(ret)

    def handle_set_stack_attribute(self, req):
        stack = req["stack"]
        ret = self.get_proxy(req["location"])
        for item in stack[:-1]:
            ret = getattr(ret, item)
        setattr(ret, stack[-1], req["value"])
        return True

    def handle_call_stack_attribute(self, req):
        stack = req["stack"]
        isolate = req.get("isolate", False)

        if req.get('location'):
            ret = self.get_proxy(req["location"])
        else:
            ret = getattr(builtins, stack[0])
            stack = stack[1:]
        for item in stack:
            ret = getattr(ret, item)
        if not isolate:
            return ret(
                *req.get("args") or [],
                **req.get("kwargs") or {}
            )
        else:
            t = Thread(
                target=ret,
                args=req.get("args") or [],
                kwargs=req.get("kwargs") or {}
            )
            t.start()
            return True

    def __format_kwargs(self, data):
        ret = {}
        for key, item in data.items():
            if isinstance(item, dict) and ("location" in item):
                ret[key] = self.get_proxy(item["location"])
            else:
                ret[key] = item
        return ret

    def handle_execute(self, req):
        return exec(
            req["code"], globals(),
            self.__format_kwargs(req["locals"])
        )

    def handle_evaluate_code(self, req):
        return eval(
            req["code"], globals(),
            self.__format_kwargs(req["locals"])
        )

    # def handle_import(self, req):
    #     target = req["item"]

    #     module = target.split(":")[0] if ":" in target else target

    #     handle = None
    #     if target and (
    #         (
    #           self.allowed_imports is not None and
    #           module in self.allowed_imports) or
    #           (module not in self.disallowed_imports)
    #     ):
    #         try:
    #             target = load_module(target)
    #         except Exception as e:
    #             return {
    #                 "type": None,
    #                 "value": None,
    #                 "error": str(e).replace('"', "'")
    #             }
    #         t = str(type(target).__name__)
    #         if isinstance(target, BaseBridgeProxy):
    #             target = target.__data__["location"]
    #             t = "bridge_proxy"
    #         elif not isinstance(
    #             target,
    #             (int, str, dict, set, tuple, bool, float, NoneType)
    #         ):
    #             handle = self.proxy_object(target)
    #             target = None

    #         if t in ["function", "method"]:
    #             t = "callable_proxy"
    #         try:
    #             return {"type": t, "value": target, "location": handle}
    #         except Exception:
    #             return {"type": t, "value": str(target), "location": handle}
    #     return {"type": None, "value": None, "error": True}

    # def handle_builtin(self, req):
    #     target = req["item"]
    #     handle = None
    #     if target and (
    #         (
    #           self.allowed_builtins is not None and
    #           target in self.allowed_builtins) or
    #           (target not in self.disallowed_builtins)
    #     ):
    #         target = load_module(f"builtins:{target}")
    #         t = str(type(target).__name__)
    #         if isinstance(target, BaseBridgeProxy):
    #             target = target.__data__["location"]
    #             t = "bridge_proxy"
    #         elif not isinstance(
    #             target,
    #             (int, str, dict, set, tuple, bool, float, NoneType)
    #         ):
    #             handle = self.proxy_object(target)
    #             target = None

    #         if t in ["function", "method", "builtin_function_or_method"]:
    #             t = "callable_proxy"
    #         try:
    #             return {"type": t, "value": target, "location": handle}
    #         except Exception:
    #             return {"type": t, "value": str(target), "location": handle}
    #     return {"type": None, "value": None, "error": True}

    def handle_get_proxy_attributes(self, req):
        target_attr = req.get("location", None)
        target = self.get_proxy(target_attr)
        if target:
            return {"value": dir(target)}

    def handle_get_proxy_attribute(self, req):
        target_attr = req.get("location", None)
        target = self.get_proxy(target_attr)
        return getattr(target, req["target"])

    def handle_set_proxy_attribute(self, req):
        target_attr = req.get("location", None)
        target = self.get_proxy(target_attr)
        if target:
            try:
                setattr(target, req["target"], req["value"])
                return {"value": True}
            except Exception as e:
                return {
                    "type": None,
                    "value": None,
                    "error": str(e).replace('"', "'")
                }
        return {"value": False}

    def handle_delete_proxy_attribute(self, req):
        target_attr = req.get("location", None)
        target = self.get_proxy(target_attr)
        if target:
            try:
                value = delattr(target, req["target"])
                return {"value": value}
            except Exception as e:
                return {
                    "type": None,
                    "value": None,
                    "error": str(e).replace('"', "'")
                }
        return {"type": None, "value": None, "error": True}

    def handle_has_proxy_attribute(self, req):
        target_attr = req.get("location", None)
        target = self.get_proxy(target_attr)
        if target:
            try:
                value = hasattr(target, req["target"])
                return {"value": value}
            except Exception as e:
                return {
                    "type": None,
                    "value": None,
                    "error": str(e).replace('"', "'")
                }
        return {"type": None, "value": None, "error": True}

    def handle_call_proxy(self, req):
        target_attr = req.get("location", None)
        target = self.get_proxy(target_attr)
        if target:
            return target(
                *req.get("args", []),
                **req.get("kwargs", {})
            )

    def handle_delete_proxy(self, req):
        target_attr = req.get("location", None)
        if target_attr:
            try:
                self.proxies.pop(target_attr, False)
                return {"value": True}
            except Exception as e:
                return {
                    "type": None,
                    "value": None,
                    "error": str(e).replace('"', "'")
                }
        return {"type": None, "value": None, "error": True}

    def get_result(self, data):
        func = self.formatters.get(data.get("obj_type"))

        if isinstance(data, dict):
            is_proxy = data.get("type") == "bridge_proxy"
            # if data.get("value", UNDEFINED) != UNDEFINED:
            #     return data["value"]
            if func:
                return func(data)
            if is_proxy and data.get("location", UNDEFINED) != UNDEFINED:
                if data.get("reverse"):
                    return self.handle_get_stack_attribute(data)
                return self.proxy(self, data)
            # elif data.get("error", UNDEFINED) != UNDEFINED:
            #     raise Exception(data["error"])
        return data
