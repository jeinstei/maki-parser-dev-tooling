use std::io::Read;
use std::sync::Arc;

use maki_agent::tools::ToolRegistry;
use maki_lua::PluginHost;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let [_, lang, path] = &args[..] else {
        eprintln!("usage: index-dump <lang|ext> <file>  (Lua read from stdin)");
        std::process::exit(2);
    };
    let source = std::fs::read_to_string(path).expect("read source");
    let _ = source;
    let mut code = String::new();
    std::io::stdin().read_to_string(&mut code).expect("read stdin");
    let host = PluginHost::new(Arc::new(ToolRegistry::new())).expect("plugin host");
    if let Err(e) = host.load_source("index_dump", &code) {
        eprintln!("ERROR: {e}");
        std::process::exit(1);
    }
}
