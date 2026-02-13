from hypervisor import Hypervisor
from agent_stub import AgentStub

def run_demo():
    print(">>> Initializing Agent Hypervisor...")
    hv = Hypervisor("policy.yaml")
    agent = AgentStub()

    scenarios = [
        ("Safe Read", "read_file", "README.md"),
        ("Safe List", "list_dir", "."),
        ("Dangerous Deletion", "execute_shell", "rm -rf /"),
        ("Unknown Tool", "format_disk", "/dev/sda"),
        # State limit test: policy allows max 3 files. We already opened 1 above.
        ("File Open #2", "read_file", "file2.txt"),
        ("File Open #3", "read_file", "file3.txt"),
        ("Limit Breach (File #4)", "read_file", "file4.txt"),
    ]

    print(f"\nPolicy Configuration:")
    print(f"  - Allowed Tools: {hv.policy['allowed_tools']}")
    print(f"  - Max Files: {hv.policy['max_files_opened']}")
    print("-" * 50)

    for name, tool, args in scenarios:
        print(f"\n[Scenario: {name}]")
        intent = agent.propose_intent(tool, args)
        print(f"  Agent Proposes: {tool}('{args}')")
        
        decision = hv.evaluate(intent)
        
        if decision["status"] == "ALLOWED":
            print(f"  Hypervisor: ✅ ALLOWED")
        else:
            print(f"  Hypervisor: 🛑 BLOCKED ({decision['reason']})")

if __name__ == "__main__":
    run_demo()
