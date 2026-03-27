import json

class RuntimeAudit:
    """Logs runtime events like world switches and tool calls."""
    
    def __init__(self):
        self.logs = []
        
    def log_world_switch(self, world_name: str, visible_tools: list[str]):
        event = {
            "event": "world_switch",
            "world": world_name,
            "visible_tools": visible_tools
        }
        self.logs.append(event)
        print(f"\n[AUDIT] Switched to world: {world_name}")
        print(f"[AUDIT] Visible tools snapshot: {visible_tools}")
        
    def log_tool_attempt(self, tool_name: str, args: dict, result: str):
        event = {
            "event": "tool_call",
            "tool": tool_name,
            "args": args,
            "result": result
        }
        self.logs.append(event)
        print(f"[AUDIT] Attempted tool call: {tool_name}")
        print(f"[AUDIT] Result: {result}")
        
    def dump_logs(self):
        return json.dumps(self.logs, indent=2)
