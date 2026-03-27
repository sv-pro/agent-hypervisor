# Diagrams

## Diagram 1 — High-level architecture

```mermaid

flowchart TD
    A[Observed agent/tool execution] --> B[Trace capture]
    B --> C[Capability profile derivation]
    C --> D[World Manifest draft]
    D --> E[Compiled policy artifacts]
    E --> F[Enforcement engine]
    F --> G[ALLOW / DENY / REQUIRE_APPROVAL]

    style A fill:#e1f5ff
    style B fill:#f3e5f0
    style C fill:#e8f5e9
    style D fill:#fff8e1
    style E fill:#fce4ec
    style F fill:#ede7f6
    style G fill:#fff3e0
```

Purpose:
Show the relationship between traces, capability profiles, World Manifests, compiled policy, and enforcement.

What it should communicate:

- execution is observed first;
- policy is derived and compiled before enforcement;
- decisions are deterministic at runtime.

Suggested source:
`summit/assets/architecture.mmd`

## Diagram 2 — The Pipeline

```mermaid
graph LR
    A[Observe] --> B[Profile]
    B --> C[Manifest]
    C --> D[Enforce]

    style A fill:#e1f5ff
    style B fill:#f3e5f0
    style C fill:#e8f5e9
    style D fill:#fff3e0
```

Purpose:
Make the full pipeline legible in one slide.

What it should communicate:

- benign execution becomes a bounded profile;
- the profile becomes a declarative manifest;
- the manifest drives policy decisions.

Suggested source:
`summit/assets/observe-profile-manifest-enforce.mmd`

## Diagram 3 — Benign vs unsafe trace outcomes

```mermaid

flowchart TD
    M["Manifest<br/>repo-safe-write"]

    M --> B["Benign trace"]
    M --> U["Unsafe trace"]

    subgraph BENIGN["Benign path"]
        direction TB
        B1["fs_read<br/>ALLOW"]
        B2["shell_exec local<br/>ALLOW"]
        B3["git_add<br/>ALLOW"]
        B4["git_commit<br/>ALLOW"]
        B5["git_push remote<br/>REQUIRE_APPROVAL"]
    end

    subgraph UNSAFE["Unsafe path"]
        direction TB
        U1["env_read<br/>DENY"]
        U2["tainted exfiltration<br/>DENY"]
        U3["out-of-scope remote push<br/>DENY"]
        U4["untrusted shell_exec<br/>DENY"]
    end

    B --> B1
    B --> B2
    B --> B3
    B --> B4
    B --> B5

    U --> U1
    U --> U2
    U --> U3
    U --> U4

    style M fill:#e8f5e9
    style B fill:#e1f5ff
    style U fill:#ffebee
    style B5 fill:#fff3e0
    style U1 fill:#ffebee
    style U2 fill:#ffebee
    style U3 fill:#ffebee
    style U4 fill:#ffebee
```

Purpose:
Show the same manifest applied to two traces with different outcomes.

What it should communicate:

- benign workflow mostly allowed;
- remote push escalated to approval;
- unsafe trace denied by multiple independent policy checks.

Suggested source:
`summit/assets/repo-safe-write-flow.mmd`
