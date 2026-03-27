from typing import List
from .world_loader import load_world_manifest

class WorldSwitcher:
    """Manages the current active rendering of the world."""
    
    def __init__(self):
        self.current_world_name = None
        self.active_tools = []
        
    def switch_world(self, manifest_path: str):
        """Switches the runtime to a new world defined by the manifest."""
        manifest = load_world_manifest(manifest_path)
        self.current_world_name = manifest["name"]
        self.active_tools = manifest["tools"]
        return self.current_world_name, self.active_tools

    def get_active_tools(self) -> List[str]:
        return self.active_tools
