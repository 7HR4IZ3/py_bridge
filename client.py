import queue
from .transporters import transporters
from .base import BaseHandler
from .utils import load_module


class PyBridgeClient(BaseHandler):
    def __init__(self, options=None):
        self.options = options or {}
        super().__init__()

    def start(self):
        transporter = transporters[self.options.get("mode")]
        if not transporter:
            raise Exception(
                "ArgumentError: Invalid mode specified."
            )

        self.transporter = transporter()

        self.transporter_queue = queue.Queue()

        self.transporter.start_client(
            self.on_message,
            self.options,
            self
        )

    def on_message(self, data):
        raw = False

        if (data.get("action")):
            if (data["action"] == "get_primitive"):
                res = self.handle_get_primitive(data)
                raw = True
                ret = {'value': res, 'type': type(res)}
            else:
                try:
                    response = self.process_command(data)
                    if data.get("stack", []) == ["tuple"]:
                        response["response"] = self.generate_proxy(
                            response['response']
                        )
                    # print("Data:", data, "Response:", response)
                    # if isinstance(
                    #     response, dict
                    # ) and isinstance(
                    #     response.get("value"), dict
                    # ):
                    #     response = response["value"]
                    ret = response
                except Exception as err:
                    ret = {'error': repr(err)}

            ret["message_id"] = data['message_id']
            self.send(**ret, raw=raw)
        elif (data.get('message_id')):
            handler = self.message_handlers.get(data['message_id'])
            if (handler):
                handler(data)
        return

    def handle_import(self, req):
        target = req["value"]
        return load_module(target, catch_error=False)
