# Python to JavaScript Bridge

The Python to JavaScript Bridge is a library that allows you to communicate between Python and other programming languages such as JavaScript, C#, Java and Golang. 

## Features

- Easy integration with multiple programming languages.
- Simplifies communication between programming languages.
- Supports different transport protocols such as sockets.

## Installation

The Python to JavaScript Bridge library can be installed using pip. Open a terminal or command prompt and enter the following command:

```bash
pip install py-bridge
```

## Usage

Here is an example of using the Python to JavaScript Bridge library to communicate with different programming languages.

```python
from py_bridge import *

node_server = NodeBridgeServer(
    SocketBridgeTransporter(),
    keep_alive=False
)

# Only nodejs supported for now.

# csharp_server = CSharpBridgeServer()
# java_server = JavaBridgeServer()
# golang_server = GoLangBridgeServer()

with node_server.setup() as node:
  node.console.log("Hello World")

# with csharp_server.setup() as csharp:
#     csharp.Console.WriteLn("Hello From Csharp")

# with java_server.setup() as java:
#     java.System.Console.WriteLn("Hello From Java")

# with golang_server.setup() as go:
#     go.import_("fmt")
#     go.fmt.PrintLn("Hello From Golang")
```

In this example, we are using the Node.js server to communicate with JavaScript, and the CSharp, Java, and Golang servers to communicate with their respective programming languages. The `keep_alive` parameter is set to `False`, meaning that the connection will be closed after the script is executed.

Each server's `setup` method is called with a `with` statement, which creates a context where we can run commands on the server. In this example, we are using each server's console to print a message.

## Conclusion

The Python to JavaScript Bridge library makes it easy to communicate between Python and other programming languages. It simplifies the communication process and supports multiple transport protocols, making it a versatile and powerful tool for developers.
