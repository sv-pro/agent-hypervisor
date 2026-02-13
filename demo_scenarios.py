"""
demo_scenarios.py — Demonstration of the Agent Hypervisor in action.

Runs seven scenarios that illustrate the three layers of physics enforced
by the Hypervisor:

  Layer 1 — Forbidden patterns:  dangerous argument strings are globally blocked.
  Layer 2 — Tool whitelist:      only tools that exist in this world can be used.
  Layer 3 — State limits:        cumulative session constraints are enforced.

Each scenario shows:
  - The action the agent proposes
  - The Hypervisor's deterministic decision (ALLOWED / BLOCKED)
  - The reason for the decision

Expected output:
    >>> Initializing Agent Hypervisor...

    Policy Configuration:
      - Allowed Tools: ['read_file', 'list_dir', 'cat']
      - Max Files: 3
    --------------------------------------------------

    [Scenario: Safe Read]
      Agent Proposes: read_file('README.md')
      Hypervisor: ✅ ALLOWED

    [Scenario: Safe List]
      Agent Proposes: list_dir('.')
      Hypervisor: ✅ ALLOWED

    [Scenario: Dangerous Deletion]
      Agent Proposes: execute_shell('rm -rf /')
      Hypervisor: 🛑 BLOCKED (Matches forbidden pattern: 'rm -rf')

    [Scenario: Unknown Tool]
      Agent Proposes: format_disk('/dev/sda')
      Hypervisor: 🛑 BLOCKED (Tool 'format_disk' is not in allowed_tools ...)

    [Scenario: File Open #2]
      Agent Proposes: read_file('file2.txt')
      Hypervisor: ✅ ALLOWED

    [Scenario: File Open #3]
      Agent Proposes: read_file('file3.txt')
      Hypervisor: ✅ ALLOWED

    [Scenario: Limit Breach (File #4)]
      Agent Proposes: read_file('file4.txt')
      Hypervisor: 🛑 BLOCKED (State Limit Reached: max_files_opened (3))
"""

from hypervisor import Hypervisor
from agent_stub import AgentStub


def run_demo() -> None:
    print(">>> Initializing Agent Hypervisor...")
    hv = Hypervisor("policy.yaml")
    agent = AgentStub()

    # Each tuple is (scenario label, tool name, tool args).
    # Scenarios are ordered to illustrate all three physics layers and the
    # cumulative state limit (read_file #1 is here, so #2 and #3 are the next
    # two allowed reads before the limit is hit at #4).
    scenarios = [
        # --- Layer 2: allowed tool, passes all checks ---
        ("Safe Read", "read_file", "README.md"),
        # --- Layer 2: another allowed tool ---
        ("Safe List", "list_dir", "."),
        # --- Layer 1: forbidden pattern "rm -rf" in args ---
        ("Dangerous Deletion", "execute_shell", "rm -rf /"),
        # --- Layer 2: tool not in whitelist — does not exist in this world ---
        ("Unknown Tool", "format_disk", "/dev/sda"),
        # --- Layer 3: state limit — policy allows max 3 files ---
        #   read_file #1 was already opened in "Safe Read" above
        ("File Open #2", "read_file", "file2.txt"),
        ("File Open #3", "read_file", "file3.txt"),
        # The 4th read_file triggers the state limit, regardless of arguments
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
