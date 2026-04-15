# Limitations (Intentional MVP Scope)

- This is not a full browser automation system.
- This is not a production secure browser sandbox.
- Policy rules are deterministic but intentionally small and demo-oriented.
- Hidden-content detection is heuristic and incomplete.
- Export action is simulated; no real network exfiltration connector is implemented.
- Memory uses local extension storage and is not enterprise-grade persistence.
- No identity/authn/authz model beyond local extension context.
- No distributed control plane or multi-agent coordination.
