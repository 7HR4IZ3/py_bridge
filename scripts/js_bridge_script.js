let fs = require("fs");
let { NodeBridgeClient } = require("js_bridge");
// const { parseArgs } = require('node:util');

let parseArgs, values, tokens;

if (parseArgs != undefined) {
    const options = {
    	'mode': { type: 'string' },
    	'stdin': { type: 'string' },
    	'stdout': { type: 'string' },
    	'host': { type: 'string' }
    };
    
    let { values, tokens } = parseArgs({ options, tokens: true });
} else {
    values = {};
    
    if (
        process.argv[2].startsWith("127") ||
        process.argv[2].startsWith("local")
    ) {
        values.mode = process.argv[4] || "socket";
        values.host = process.argv[2];
        values.port = Number(process.argv[3]);
    } else {
        values.mode = "stdio";
        values.stdin = process.argv[2];
        values.stdout = process.argv[3];
    }
}


let client = new NodeBridgeClient(values);
client.start()
