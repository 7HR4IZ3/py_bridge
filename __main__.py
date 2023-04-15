import argparse
from .client import PyBridgeClient

parser = argparse.ArgumentParser()

parser.add_argument("--mode", help="Transporter type.")
parser.add_argument("--host", help="Transporter host.")
parser.add_argument("--port", help="Transporter port.", type=int)

args = parser.parse_args()
client = PyBridgeClient({
    "mode": args.mode,
    "host": args.host,
    "port": args.port
})
client.start()
