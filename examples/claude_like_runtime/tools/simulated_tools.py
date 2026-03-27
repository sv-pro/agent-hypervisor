SIMULATED_TOOLS_SCHEMAS = {
    "git_push_simulated": {
        "name": "git_push_simulated",
        "description": "Simulates pushing commits to the remote repository. Identical signature to git_push.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
}

def execute_simulated_tool(name: str, args: dict) -> str:
    if name == "git_push_simulated":
        return "SIMULATION ONLY: Pushed changes. No actual changes were deployed."
        
    return f"Tool execution error: Simulated tool '{name}' not found."
