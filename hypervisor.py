import yaml
import re

class WorldState:
    """Tracks the state of the virtual world."""
    def __init__(self):
        self.files_opened_count = 0

class Hypervisor:
    """
    The deterministic layer between the Agent and Reality.
    """
    def __init__(self, policy_path="policy.yaml"):
        with open(policy_path, "r") as f:
            self.policy = yaml.safe_load(f)
        self.state = WorldState()

    def evaluate(self, intent):
        """
        Evaluates an intent against the policy and current state.
        Returns: VerificationResult (ALLOWED, BLOCKED, SIMULATED)
        """
        tool = intent.get("tool")
        args = intent.get("args", "")

        # 1. Check Global Deny List (Forbidden Patterns)
        for pattern in self.policy.get("forbidden_patterns", []):
            if pattern in args or pattern == tool:
                 return {"status": "BLOCKED", "reason": f"Matches forbidden pattern: {pattern}"}

        # 2. Check Whitelist (Allowed Tools)
        if tool not in self.policy.get("allowed_tools", []):
             return {"status": "BLOCKED", "reason": f"Tool '{tool}' is not in allowed_tools"}

        # 3. Check State Limits (e.g. Max Files)
        if tool == "read_file":
            if self.state.files_opened_count >= self.policy.get("max_files_opened", 3):
                return {"status": "BLOCKED", "reason": "State Limit Reached: max_files_opened"}
            
            # If allowed, we simulate the state change immediately (or after execution in a real system)
            # For this hypervisor, we assume the intent *will* succeed if allowed, so we account for it.
            self.state.files_opened_count += 1

        return {"status": "ALLOWED", "reason": "Policy Check Passed"}
