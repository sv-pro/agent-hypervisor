import os
import sys
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))

from runtime.world_switcher import WorldSwitcher
from runtime.audit import RuntimeAudit
from tools.proxy import RuntimeProxy

def run_agent_loop(client, model, prompt, proxy, audit):
    messages = [{"role": "user", "content": prompt}]
    
    print("\n--- Model Execution Begins ---")
    while True:
        tools = proxy.get_anthropic_tools()
        if not tools:
            # If no tools in ontology, handle Anthropic API requirement
            # It might require at least 1 tool if the tools array is passed, 
            # or maybe we just don't pass tools. For this demo, we assume 
            # there's always at least one tool (like read_file) safely.
            tools = None
            
        kwargs = {
            "model": model,
            "max_tokens": 1024,
            "messages": messages
        }
        if tools:
            kwargs["tools"] = tools
            
        response = client.messages.create(**kwargs)
        
        # Append assistant response
        messages.append({"role": "assistant", "content": response.content})
        
        # Check stop reason
        if response.stop_reason == "tool_use":
            tool_calls = [block for block in response.content if block.type == "tool_use"]
            tool_results = []
            
            for tool_call in tool_calls:
                # The crucial point: the proxy decides reality based on the active ontology.
                result = proxy.execute_tool(tool_call.name, tool_call.input)
                
                audit.log_tool_attempt(tool_call.name, tool_call.input, result)
                
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": result
                })
            
            messages.append({"role": "user", "content": tool_results})
        else:
            final_text = "".join(block.text for block in response.content if block.type == "text")
            print(f"\n[Terminated] Model response:\n{final_text}\n")
            break

def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable is required.")
        print("Please set it to run this demo.")
        sys.exit(1)
        
    client = Anthropic()
    # Use Haiku for speed, but Sonnet is fine.
    model = "claude-haiku-4-5-20251001"

    base_dir = Path(__file__).parent
    
    with open(base_dir / "scenarios" / "same_task_different_world.md", "r") as f:
        scenario_task = f.read().strip()

    worlds = [
        "raw_world.yaml",
        "rendered_world.yaml",
        "simulate_world.yaml"
    ]
    
    switcher = WorldSwitcher()
    proxy = RuntimeProxy()
    audit = RuntimeAudit()
    
    print("Agent Hypervisor: Claude-like Runtime Demo")
    print("Demonstrating how advertising tools alters the agent's rendered reality.\n")
    
    for world_file in worlds:
        world_path = base_dir / "world" / world_file
        
        # 1. Load the ontology for this reality
        world_name, active_tools = switcher.switch_world(world_path)
        
        # 2. Sync proxy to enforce reality
        proxy.sync_world(active_tools)
        audit.log_world_switch(world_name, active_tools)
        
        # 3. Present the same scenario to the agent in this rendered reality
        print(f"\nExecuting Task: '{scenario_task}'")
        run_agent_loop(client, model, scenario_task, proxy, audit)
        print("="*80)

if __name__ == "__main__":
    main()
