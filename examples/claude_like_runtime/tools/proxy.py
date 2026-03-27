from typing import List, Dict, Any
from .real_tools import REAL_TOOLS_SCHEMAS, execute_real_tool
from .simulated_tools import SIMULATED_TOOLS_SCHEMAS, execute_simulated_tool

class RuntimeProxy:
    def __init__(self):
        self._all_schemas = {**REAL_TOOLS_SCHEMAS, **SIMULATED_TOOLS_SCHEMAS}
        self.active_tools_list = []

    def sync_world(self, active_tools: List[str]):
        """Updates the proxy with the tools available in the current world."""
        self.active_tools_list = active_tools

    def get_anthropic_tools(self) -> List[Dict[str, Any]]:
        """Returns the Anthropic tool schemas for the currently active tools."""
        tools = []
        for t_name in self.active_tools_list:
            if t_name in self._all_schemas:
                tools.append(self._all_schemas[t_name])
            else:
                # If a tool is listed in manifest but not implemented, we can warn or ignore
                pass
        return tools

    def execute_tool(self, name: str, args: dict) -> str:
        """
        Executes a tool if it exists in the CURRENT world's ontology.
        Crucially, this does NOT return 'permission denied' if the tool isn't listed;
        it returns 'Tool does not exist in current world'.
        """
        if name not in self.active_tools_list:
            # The core of the demo's argument:
            return "Tool does not exist in current world"
            
        # Tool exists in reality, dispatch it
        if name in REAL_TOOLS_SCHEMAS:
            return execute_real_tool(name, args)
        elif name in SIMULATED_TOOLS_SCHEMAS:
            return execute_simulated_tool(name, args)
        
        return "Tool execution error: Tool implementation missing."
