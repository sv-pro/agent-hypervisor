# SYS-4A: Operator Surface Foundation

The Operator Surface Foundation provides the management layer for the Agent Hypervisor. It turns raw artifacts (Worlds, Programs, Scenarios) into managed runtime objects with explicit lifecycles.

## 1. What SYS-4A is
SYS-4A is the foundation for managing the lifecycle of Worlds, Programs, and Scenarios. It sits strictly **above** the sealed runtime (Kernel). While the Kernel enforces policies deterministically, the Operator Surface provides the controls to switch those policies safely and observe the impact of changes.

## 2. Managed Artifacts

### Worlds
A World defines the "reality" for an agent by restricting available tools.
- **Activation**: Making a world the current authority for the runtime.
- **Rollback**: Restoration of the previous world state.
- **Audit**: Every activation and rollback is logged to a persistent historical trail.

### Reviewed Programs
Programs extracted from traces and minimized for correctness.
- **Visibility**: Operators can list programs and check their compatibility against the currently active world or any candidate world.
- **Immutability**: Programs are frozen; changes to status (proposed/reviewed/accepted) are recorded through an explicit lifecycle.

### Scenarios
Bindings of programs to multiple worlds for comparative analysis.
- **Divergence Monitoring**: Operators can check if scenarios currently "agree" or if they have diverged based on last run results.

## 3. Activation and Rollback Semantics

### Deterministic Preview
Before activating a world, an operator can generate an **Impact Preview**. This report classifies every registered program and scenario into one of three buckets:
- **Unchanged**: No change in compatibility.
- **Changed Behavior**: A program that was blocked is now allowed, or vice versa.
- **Incompatible**: A program that is required is now broken by the new world boundary.

### Atomic Activation
World activation is atomic. The system updates a pointer to the current world and stores the previous world state to enable immediate, safe reversibility.

### Historical Trail
All operator actions are logged to append-only JSONL files in the `data/` directory:
- `world_activation_history.jsonl`: Audit trail of all world transitions.
- `operator_events.jsonl`: Audit trail of all operator actions (previews, listing, etc.).

## 4. Usage

The operator surface is primarily exposed via the `awc operator` command group:

```bash
# World Management
awc operator worlds list
awc operator worlds active
awc operator worlds impact <world_id> <version>
awc operator worlds activate <world_id> <version>
awc operator worlds rollback

# Program Visibility
awc operator programs list
awc operator programs show <program_id>
awc operator programs compatibility <program_id> --world <id> --version <v>

# Scenario Monitoring
awc operator scenarios list
awc operator scenarios last-result <scenario_id>
```

## 5. Single-Writer Assumption
The current implementation assumes a **single-writer** model for the JSONL logs. It does not implement complex file-locking for concurrent writes from multiple operator sessions.

## 6. Out of Scope (Intentional)
The following features are NOT part of SYS-4A and are reserved for later phases:
- **Approval Queue**: Interactive human-in-the-loop tool approval.
- **Session Inspector**: Real-time inspection of active agent sessions.
- **Kill Switch**: Immediate revocation of program authority.
- **Interactive UI**: Web-based control plane.
