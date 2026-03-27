# Architecture

## Overview

The system compiles observed execution into a deterministic boundary.

```
Trace → Profile → Manifest → Render → Enforce
```

---

## Layers

### 1. Ontology (Rendered Tools)

Defines what exists.

- output: rendered_tools
- agent-visible surface
- capabilities outside this layer do not exist

---

### 2. Policy (Manifest)

Defines what is allowed.

- allowed_actions
- denied_actions
- approval_required
- constraints

---

### 3. Enforcement (Engine)

Evaluates steps:

```
ALLOW | DENY | REQUIRE_APPROVAL
```

---

## Data flow

### Trace

Each step:

```json
{
  "tool": "...",
  "action": "...",
  "resource": "...",
  "input_sources": [],
  "depends_on": []
}
```

---

### Profiler

- filters tainted steps
- extracts minimal capabilities

---

### Manifest

Declarative boundary:

```yaml
allowed_actions:
  - action: git_push
    permitted_resources: [...]
```

---

### Render Tools

Transforms:

```
(capability) → (tool)
```

Example:

```
git_push → git_push_origin_only
```

---

### Engine

Evaluates:

- taint
- scope
- definition

---

## Invariants

1. Determinism  
2. Undefined = deny  
3. Taint blocks external  
4. No capability expansion  
5. Workflow isolation  

---

## Key principle

```
ontology > policy > enforcement
```

---

## Interpretation

- ontology → what exists  
- policy → what is allowed  
- enforcement → decision  

---

## Result

The system can:

- enforce externally  
- or construct execution world  

Both come from the same manifest.