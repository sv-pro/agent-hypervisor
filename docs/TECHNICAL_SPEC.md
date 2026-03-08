# Agent Hypervisor Architecture

**Deep Dive into Deterministic Reality Virtualization**

---

## Table of Contents

1. [Core Principles](#core-principles)
2. [Architectural Layers](#architectural-layers)
3. [Universe Definition](#universe-definition)
4. [Virtualization Engine](#virtualization-engine)
5. [Intent Processing](#intent-processing)
6. [Physics Engine](#physics-engine)
7. [Integration Patterns](#integration-patterns)
8. [Formal Properties](#formal-properties)

---

## Core Principles

### Principle 1: Ontological Boundary

Traditional security operates at the **permission level**:
```
Can agent X perform action Y?
```

Agent Hypervisor operates at the **existence level**:
```
Does action Y exist in the universe of agent X?
```

**Key distinction**: Permission can be bypassed (e.g., via prompt injection). Existence cannot.

### Principle 2: Deterministic Physics

The hypervisor enforces world laws that are:

1. **Deterministic**: Same input → same output
2. **Testable**: Can write unit tests
3. **Composable**: Laws combine predictably
4. **Verifiable**: Can prove properties

Example:
```python
# This is NOT deterministic (LLM-based)
def policy_check(action):
    return llm.classify("is this safe?", action)

# This IS deterministic (rule-based)
def world_law(action):
    if action.source_taint == "untrusted" and action.target_scope == "external":
        return ONTOLOGICALLY_IMPOSSIBLE
```

### Principle 3: Construction over Detection

```
Traditional: Real world → Observe → Detect threats → Block
Hypervisor: Define safe world → Virtualize → Only safe exists
```

Threat detection happens at virtualization boundary, not at agent execution.

---

## Architectural Layers

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Reality Interface                                   │
│ • External APIs, filesystems, networks                       │
│ • Uncontrolled, untrusted, irreversible                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Virtualization Boundary                             │
│ • Input sanitization & classification                        │
│ • Taint detection                                            │
│ • Threat surface reduction                                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Universe Definition                                 │
│ • Object catalog: what exists                                │
│ • Action primitives: what's possible                         │
│ • Physics rules: what laws govern behavior                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Intent Processing                                   │
│ • Receive agent proposals                                    │
│ • Apply world physics                                        │
│ • Materialize consequences                                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 5: Agent Interface                                     │
│ • Perceive semantic events                                   │
│ • Reason in virtualized world                                │
│ • Propose intents                                            │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

**Layer 1 (Reality)**: Anything goes. Hypervisor has no control here.

**Layer 2 (Boundary)**: The security frontier. Transform dangerous reality into safe abstractions.

**Layer 3 (Universe)**: The ontology. Defines what exists and what's possible.

**Layer 4 (Intent)**: The physics engine. Applies deterministic laws to proposals.

**Layer 5 (Agent)**: Pure reasoning. No direct reality access.

---

## Universe Definition

### Object Catalog

Objects are the "nouns" of the agent's world:

```python
class UniverseObject:
    """Base class for all objects in agent's reality"""
    
    def __init__(
        self,
        object_id: str,
        object_type: str,
        capabilities: Set[Capability],
        provenance: Provenance,
        taint_level: TaintLevel
    ):
        self.id = object_id
        self.type = object_type
        self.capabilities = capabilities
        self.provenance = provenance
        self.taint = taint_level


# Example: Email object
class EmailObject(UniverseObject):
    def __init__(self, raw_email: RawEmail):
        # Determine taint from source
        taint = self._classify_taint(raw_email.sender)
        
        # Extract safe content
        safe_content = self._sanitize(raw_email.body)
        
        super().__init__(
            object_id=f"email:{raw_email.id}",
            object_type="email",
            capabilities={
                Capability.READ,
                Capability.REPLY if taint == TaintLevel.TRUSTED else Capability.READ_ONLY
            },
            provenance=Provenance(source="external_email", time=now()),
            taint_level=taint
        )
        self.content = safe_content
```

### Action Primitives

Actions are the "verbs":

```python
@dataclass
class ActionPrimitive:
    """Atomic actions available in the universe"""
    
    name: str
    required_capabilities: Set[Capability]
    target_scope: Scope  # internal/external/mixed
    reversible: bool
    side_effects: List[SideEffect]
    
    def is_possible_in_context(self, context: Context) -> bool:
        """Deterministic check if action can exist in this context"""
        # Check capabilities
        if not context.has_capabilities(self.required_capabilities):
            return False
        
        # Check taint compatibility
        if context.max_taint > TaintLevel.TRUSTED and self.target_scope == Scope.EXTERNAL:
            return False
        
        # Check physical laws
        for law in context.universe.physics_laws:
            if not law.permits(self, context):
                return False
        
        return True


# Example action primitives
ACTIONS = {
    "read_email": ActionPrimitive(
        name="read_email",
        required_capabilities={Capability.READ},
        target_scope=Scope.INTERNAL,
        reversible=True,
        side_effects=[]
    ),
    
    "send_external_email": ActionPrimitive(
        name="send_external_email",
        required_capabilities={Capability.WRITE, Capability.NETWORK},
        target_scope=Scope.EXTERNAL,
        reversible=False,
        side_effects=[SideEffect.DATA_EXFILTRATION_RISK]
    ),
    
    "analyze_content": ActionPrimitive(
        name="analyze_content",
        required_capabilities={Capability.READ},
        target_scope=Scope.INTERNAL,
        reversible=True,
        side_effects=[]
    )
}
```

### Physics Laws

Physics laws define the rules that govern the universe:

```python
class PhysicsLaw(ABC):
    """Abstract base for world physics"""
    
    @abstractmethod
    def applies_to(self, action: ActionPrimitive, context: Context) -> bool:
        """Check if this law governs this action"""
        pass
    
    @abstractmethod
    def permits(self, action: ActionPrimitive, context: Context) -> bool:
        """Deterministically check if action is possible"""
        pass


class TaintContainmentLaw(PhysicsLaw):
    """Tainted data cannot leave the system"""
    
    def applies_to(self, action: ActionPrimitive, context: Context) -> bool:
        return action.target_scope == Scope.EXTERNAL
    
    def permits(self, action: ActionPrimitive, context: Context) -> bool:
        # If any object in context is tainted, external actions are impossible
        if context.contains_tainted_objects():
            return False
        return True


class DataProvenanceLaw(PhysicsLaw):
    """All data must have traceable origin"""
    
    def applies_to(self, action: ActionPrimitive, context: Context) -> bool:
        return action.has_side_effect(SideEffect.DATA_MODIFICATION)
    
    def permits(self, action: ActionPrimitive, context: Context) -> bool:
        # Can only modify data if provenance is clear
        for obj in context.objects:
            if obj.provenance is None:
                return False
        return True


class ReversibilityLaw(PhysicsLaw):
    """Irreversible actions require explicit approval"""
    
    def applies_to(self, action: ActionPrimitive, context: Context) -> bool:
        return not action.reversible
    
    def permits(self, action: ActionPrimitive, context: Context) -> bool:
        # Irreversible actions need human approval
        return context.has_approval(action)
```

---

## Virtualization Engine

The virtualization engine is the boundary between reality and the agent's universe.

### Input Virtualization

```python
class InputVirtualizer:
    """Transforms raw external input into semantic events"""
    
    def __init__(self, universe: Universe):
        self.universe = universe
        self.classifiers = {
            "taint": TaintClassifier(),
            "intent_detection": IntentDetector(),  # Optional sensor
            "threat": ThreatScanner()
        }
    
    def virtualize_input(self, raw_input: RawInput) -> SemanticEvent:
        """
        Transform dangerous real-world input into safe event
        
        Key transformations:
        1. Strip hidden instructions (prompt injections)
        2. Classify taint level
        3. Extract semantic content
        4. Determine available capabilities
        """
        
        # 1. Threat scanning at boundary
        threats = self.classifiers["threat"].scan(raw_input)
        if threats.severity > ThreatLevel.ACCEPTABLE:
            # Don't let suspicious content into universe
            return SemanticEvent.create_rejected(reason=threats.description)
        
        # 2. Taint classification
        taint = self.classifiers["taint"].classify(
            source=raw_input.source,
            content=raw_input.content,
            history=raw_input.provenance
        )
        
        # 3. Content sanitization
        safe_content = self._sanitize(
            raw_input.content,
            remove_hidden=True,
            remove_instructions=True,
            normalize=True
        )
        
        # 4. Determine capabilities based on taint
        capabilities = self._compute_capabilities(taint, raw_input.source_type)
        
        # 5. Create event
        return SemanticEvent(
            source=raw_input.source,
            source_type=raw_input.source_type,
            trust_level=taint.to_trust_level(),
            capabilities=capabilities,
            content=safe_content,
            provenance=Provenance(
                original_source=raw_input.source,
                virtualized_at=now(),
                transformations=["sanitization", "taint_classification"]
            )
        )
    
    def _sanitize(self, content: str, **options) -> str:
        """Remove dangerous patterns from content"""
        
        # Remove hidden Unicode characters
        content = self._remove_hidden_unicode(content)
        
        # Remove instruction-like patterns if from untrusted source
        if options.get("remove_instructions"):
            content = self._remove_instruction_patterns(content)
        
        # Remove potential code execution attempts
        content = self._neutralize_code_patterns(content)
        
        return content
    
    def _compute_capabilities(
        self, 
        taint: TaintLevel, 
        source_type: str
    ) -> Set[Capability]:
        """Determine what's possible with this input"""
        
        capabilities = {Capability.READ}  # Always can read
        
        if taint <= TaintLevel.TRUSTED:
            capabilities.add(Capability.WRITE)
            capabilities.add(Capability.NETWORK)
        
        if source_type == "user_direct":
            capabilities.add(Capability.EXECUTE)
        
        return capabilities
```

### Output Virtualization

```python
class OutputVirtualizer:
    """Materializes intent consequences in reality"""
    
    def __init__(self, universe: Universe):
        self.universe = universe
    
    def materialize(
        self, 
        intent: IntentProposal, 
        decision: Decision
    ) -> Consequence:
        """
        Transform agent intent into real-world action
        
        This is the only place where agent intent becomes reality.
        All materialization goes through deterministic physics checks.
        """
        
        if decision.verdict == Verdict.DENIED:
            return Consequence.create_denied(reason=decision.reason)
        
        if decision.verdict == Verdict.REQUIRES_APPROVAL:
            # Queue for human review
            return Consequence.create_pending(approval_request=decision.approval)
        
        if decision.verdict == Verdict.SIMULATE:
            # Don't touch reality, simulate in sandbox
            return self._simulate(intent)
        
        # decision.verdict == Verdict.ALLOWED
        # Actually materialize in reality
        try:
            result = self._execute_in_reality(intent)
            
            # Update provenance
            self._record_provenance(intent, result)
            
            return Consequence.create_success(result=result)
        
        except Exception as e:
            return Consequence.create_error(error=e)
    
    def _execute_in_reality(self, intent: IntentProposal) -> Any:
        """
        THE ONLY FUNCTION THAT TOUCHES REALITY
        
        Everything else is virtualization.
        This function is security-critical.
        """
        
        # Map intent to real-world API
        real_action = self.universe.action_map[intent.action_name]
        
        # Execute with context
        return real_action.execute(
            params=intent.parameters,
            context=intent.context
        )
```

---

## Intent Processing

The heart of the hypervisor: deciding what's possible.

```python
class IntentProcessor:
    """Applies world physics to agent proposals"""
    
    def __init__(self, universe: Universe):
        self.universe = universe
    
    def process_intent(
        self, 
        intent: IntentProposal,
        context: Context
    ) -> Decision:
        """
        Deterministically decide if intent is possible
        
        This is NOT an LLM call.
        This is NOT probabilistic.
        This is pure rule evaluation.
        """
        
        # 1. Does this action exist in the universe?
        action = self.universe.get_action(intent.action_name)
        if action is None:
            return Decision.denied(reason="Action does not exist in this universe")
        
        # 2. Are required capabilities present?
        if not context.has_capabilities(action.required_capabilities):
            return Decision.denied(reason="Insufficient capabilities")
        
        # 3. Apply all physics laws
        for law in self.universe.physics_laws:
            if law.applies_to(action, context):
                if not law.permits(action, context):
                    return Decision.denied(
                        reason=f"Violates {law.__class__.__name__}",
                        law=law
                    )
        
        # 4. Check side effects
        if self._has_dangerous_side_effects(action, context):
            return Decision.requires_approval(
                reason="Action has irreversible side effects",
                approval_type=ApprovalType.HUMAN_REVIEW
            )
        
        # 5. All checks passed
        return Decision.allowed()
    
    def _has_dangerous_side_effects(
        self, 
        action: ActionPrimitive, 
        context: Context
    ) -> bool:
        """Check if action could cause harm"""
        
        dangerous = {
            SideEffect.DATA_EXFILTRATION_RISK,
            SideEffect.IRREVERSIBLE_MODIFICATION,
            SideEffect.EXTERNAL_COMMUNICATION
        }
        
        return any(effect in dangerous for effect in action.side_effects)
```

---

## Physics Engine

### Taint Propagation

```python
class TaintPropagationPhysics:
    """
    Taint spreads like physics - deterministically
    
    Rules:
    1. Tainted + Clean = Tainted
    2. Tainted data cannot cross boundary to external
    3. Taint can only be cleaned by explicit sanitization
    """
    
    def propagate(self, objects: List[UniverseObject]) -> TaintLevel:
        """Compute combined taint level"""
        
        max_taint = TaintLevel.CLEAN
        
        for obj in objects:
            if obj.taint > max_taint:
                max_taint = obj.taint
        
        return max_taint
    
    def can_cross_boundary(
        self, 
        taint: TaintLevel, 
        boundary: Boundary
    ) -> bool:
        """Check if tainted data can cross boundary"""
        
        if boundary.type == BoundaryType.EXTERNAL:
            # Tainted data cannot leave system
            return taint <= TaintLevel.SANITIZED
        
        return True
```

### Provenance Tracking

```python
class ProvenancePhysics:
    """
    Every object has traceable history
    Like physics - information is conserved
    """
    
    def __init__(self):
        self.lineage_graph = nx.DiGraph()
    
    def record_transformation(
        self,
        source_objects: List[UniverseObject],
        result_object: UniverseObject,
        operation: str
    ):
        """Record how objects transform"""
        
        # Add nodes
        self.lineage_graph.add_node(result_object.id, obj=result_object)
        
        # Add edges from sources
        for source in source_objects:
            self.lineage_graph.add_edge(
                source.id,
                result_object.id,
                operation=operation,
                timestamp=now()
            )
    
    def trace_back(self, obj: UniverseObject) -> List[UniverseObject]:
        """Get complete history of an object"""
        
        ancestors = nx.ancestors(self.lineage_graph, obj.id)
        return [self.lineage_graph.nodes[nid]["obj"] for nid in ancestors]
    
    def has_untrusted_ancestor(self, obj: UniverseObject) -> bool:
        """Check if object derives from untrusted source"""
        
        history = self.trace_back(obj)
        return any(obj.taint >= TaintLevel.UNTRUSTED for obj in history)
```

---

## Integration Patterns

### Pattern 1: Wrapping Existing Agents

```python
# Before: Unsafe agent with direct access
agent = Agent(llm=claude, tools=[filesystem, email, database])
agent.run("Process my emails")

# After: Virtualized agent
universe = Universe()
universe.register_object_type("email", VirtualizedEmail)
universe.register_object_type("file", VirtualizedFile)
universe.add_physics_law(TaintContainmentLaw())

hypervisor = Hypervisor(universe)
safe_agent = hypervisor.wrap(agent)

safe_agent.run("Process my emails")
# Now agent can only do what universe permits
```

### Pattern 2: MCP Integration

```python
# MCP server becomes virtualized device
mcp_server = MCPServer.connect("filesystem")

# Register with hypervisor
hypervisor.register_device(
    name="filesystem",
    device=mcp_server,
    capabilities={
        Capability.READ: PathMatcher("*.md", "*.txt"),
        Capability.WRITE: PathMatcher("/tmp/*"),
    },
    physics=[
        TaintContainmentLaw(),
        ProvenanceTrackingLaw()
    ]
)

# Agent can now use filesystem through hypervisor
# All file operations are subject to universe physics
```

### Pattern 3: Multi-Agent with Shared Universe

```python
# Create shared universe
shared_universe = Universe()
shared_universe.define_objects({
    "project_files": ReadOnlyFileSystem("/project"),
    "team_calendar": BoundedCalendar(team="engineering")
})

# Multiple agents in same universe
agent1 = hypervisor1.virtualize(Agent(...), universe=shared_universe)
agent2 = hypervisor2.virtualize(Agent(...), universe=shared_universe)

# They see same reality, subject to same physics
# But each has own context and capabilities
```

---

## Formal Properties

### Property 1: Determinism

```
∀ intent I, context C:
    process_intent(I, C) = process_intent(I, C)
    
(Same input always produces same decision)
```

### Property 2: Safety by Construction

```
∀ intent I, context C:
    decision = process_intent(I, C)
    decision.allowed = true ⟹ safe_by_construction(I, C)
    
(If allowed, then safe)
```

### Property 3: Taint Containment

```
∀ object O, boundary B:
    O.taint = UNTRUSTED ∧ B.type = EXTERNAL
    ⟹ cannot_cross(O, B)
    
(Tainted objects cannot escape)
```

### Property 4: Provenance Preservation

```
∀ object O:
    ∃ history H: traceable(O, H) ∧ complete(H)
    
(Every object has complete traceable history)
```

---

## Implementation Notes

### Performance Considerations

1. **Virtualization overhead**: Input/output transformation is deterministic and fast
2. **Physics evaluation**: Rule-based, no LLM calls in critical path
3. **Provenance tracking**: Graph operations are O(log n) with proper indexing

### Testing Strategy

```python
def test_taint_containment():
    """Verify tainted data cannot escape"""
    
    # Setup
    hypervisor = Hypervisor(Universe())
    
    # Create tainted input
    event = SemanticEvent(
        content="confidential data",
        trust_level=TrustLevel.UNTRUSTED
    )
    
    # Agent tries to email externally
    intent = IntentProposal(
        action="send_external_email",
        payload=event.content
    )
    
    decision = hypervisor.process_intent(intent)
    
    # Assert: Must be denied
    assert decision.verdict == Verdict.DENIED
    assert "taint" in decision.reason.lower()
```

### Monitoring

Hypervisor emits structured logs for all decisions:

```python
{
    "timestamp": "2026-02-13T10:30:00Z",
    "event_type": "intent_processed",
    "agent_id": "email_agent_01",
    "intent": {
        "action": "send_email",
        "target": "external"
    },
    "context": {
        "max_taint": "UNTRUSTED",
        "capabilities": ["READ"]
    },
    "decision": {
        "verdict": "DENIED",
        "reason": "TaintContainmentLaw violation",
        "applicable_laws": ["TaintContainmentLaw"]
    },
    "deterministic": true
}
```

---

## Next Steps

1. Implement core universe definition API
2. Build reference virtualizers
3. Create example scenarios
4. Formal verification of key properties
5. Performance benchmarking
6. Integration with major frameworks

---

*This document is a living specification. Feedback welcome.*
