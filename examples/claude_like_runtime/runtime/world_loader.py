import yaml
from pathlib import Path

def load_world_manifest(filepath: str | Path) -> dict:
    """Loads a world definitions from a YAML manifest."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"World manifest not found: {path}")
    
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    return {
        "name": data.get("name", "unknown_world"),
        "description": data.get("description", ""),
        "tools": data.get("tools", [])
    }
