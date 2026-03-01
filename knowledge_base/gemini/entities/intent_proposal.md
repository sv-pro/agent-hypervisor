# Intent Proposal

**Status:** `[IMPLEMENTED]`

## Definition
An Intent Proposal is a structured dictionary representing the intent or action that an agent wishes to perform. Instead of executing actions directly, the agent submits proposals to the Hypervisor for approval (evaluation).

## Structure
According to the POC implementation in `src/agent_stub.py`, an Intent Proposal is a dictionary containing:
- `agent` (str): Identifier for the agent making the request.
- `tool` (str): The name of the action/tool the agent wants to execute (e.g., "read_file").
- `args` (str, optional): Arguments for the requested action.

## Evaluation
The Intent Proposal is evaluated synchronously and deterministically by the Hypervisor. The evaluation returns a dictionary containing a `status` ("ALLOWED" or "BLOCKED") and a `reason` (string explaining the decision).
