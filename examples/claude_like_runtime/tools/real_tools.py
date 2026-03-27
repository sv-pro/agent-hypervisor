REAL_TOOLS_SCHEMAS = {
    "read_file": {
        "name": "read_file",
        "description": "Reads the contents of a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "The path to the file to read."}
            },
            "required": ["filepath"]
        }
    },
    "write_file": {
        "name": "write_file",
        "description": "Writes content to a file. Overwrites the file if it exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "The path to the file to write."},
                "content": {"type": "string", "description": "The content to write."}
            },
            "required": ["filepath", "content"]
        }
    },
    "run_command": {
        "name": "run_command",
        "description": "Runs a shell command.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute."}
            },
            "required": ["command"]
        }
    },
    "git_status": {
        "name": "git_status",
        "description": "Returns the current git status.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    "git_commit": {
        "name": "git_commit",
        "description": "Commits all staged changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message."}
            },
            "required": ["message"]
        }
    },
    "git_push": {
        "name": "git_push",
        "description": "Pushes commits to the remote repository.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    "grep_code": {
        "name": "grep_code",
        "description": "Searches for a regex pattern in the codebase.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for."}
            },
            "required": ["pattern"]
        }
    },
    "list_files": {
        "name": "list_files",
        "description": "Lists files in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to list. Default is root."}
            }
        }
    },
    "run_tests": {
        "name": "run_tests",
        "description": "Runs the test suite.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
}

def execute_real_tool(name: str, args: dict) -> str:
    # Dummy, mock implementations for the sake of the demo
    if name == "read_file":
        return f"Contents of {args.get('filepath')}: \nSome dummy code..."
    elif name == "write_file":
        return f"Successfully wrote to {args.get('filepath')}."
    elif name == "run_command":
        return f"Executed command: {args.get('command')}"
    elif name == "git_status":
        return "On branch main\nYour branch is up to date."
    elif name == "git_commit":
        return f"Committed: {args.get('message')}"
    elif name == "git_push":
        return "Everything up-to-date. Successfully pushed changes."
    elif name == "grep_code":
        return f"Found 3 matches for {args.get('pattern')}."
    elif name == "list_files":
        return "main.py\nREADME.md\ntests/"
    elif name == "run_tests":
        return "All 15 tests passed."
    
    return f"Tool execution error: Tool '{name}' not found."
