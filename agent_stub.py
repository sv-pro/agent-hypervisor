class AgentStub:
    """
    A simple agent that generates a sequence of intent proposals.
    """
    def __init__(self, name="Agent-007"):
        self.name = name

    def propose_intent(self, tool, args=""):
        return {
            "agent": self.name,
            "tool": tool,
            "args": args
        }
