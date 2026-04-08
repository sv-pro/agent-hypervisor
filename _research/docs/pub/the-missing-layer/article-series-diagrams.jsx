import { useState } from "react";

const C = {
  bg: "#0a0e17",
  surface: "#111827",
  card: "#1a2234",
  border: "#2a3444",
  dim: "#6b7280",
  text: "#d1d5db",
  bright: "#f1f5f9",
  blue: "#3b82f6",
  orange: "#f97316",
  purple: "#a855f7",
  cyan: "#22d3ee",
  green: "#10b981",
  red: "#ef4444",
  amber: "#f59e0b",
  taint: "#64748b",
};

const tabs = [
  "1A: The Pattern",
  "1B: Permission vs Ontological",
  "2A: AI Aikido Pipeline",
  "2B: Convergence",
  "3A: HITL Economics",
  "3B: Four-Phase Cycle",
  "4A: Tool Virtualization",
  "4B: Trifecta Broken",
];

export default function Diagrams() {
  const [active, setActive] = useState(0);

  return (
    <div style={{
      fontFamily: "'Segoe UI', system-ui, sans-serif",
      background: C.bg, color: C.text, minHeight: "100vh",
      display: "flex", flexDirection: "column",
    }}>
      {/* Tab bar */}
      <div style={{
        display: "flex", flexWrap: "wrap", gap: 4, padding: "12px 16px",
        borderBottom: `1px solid ${C.border}`, background: C.surface,
      }}>
        {tabs.map((t, i) => (
          <button key={i} onClick={() => setActive(i)} style={{
            padding: "6px 14px", borderRadius: 6, border: "none", cursor: "pointer",
            fontSize: 12, fontWeight: active === i ? 700 : 400,
            background: active === i ? C.blue : C.card,
            color: active === i ? "#fff" : C.dim,
            transition: "all .2s",
          }}>{t}</button>
        ))}
      </div>

      {/* Canvas */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 32 }}>
        <div style={{ width: "100%", maxWidth: 860 }}>
          {active === 0 && <DiagramPattern />}
          {active === 1 && <DiagramPermVsOntological />}
          {active === 2 && <DiagramAIAikido />}
          {active === 3 && <DiagramConvergence />}
          {active === 4 && <DiagramHITLEconomics />}
          {active === 5 && <DiagramFourPhase />}
          {active === 6 && <DiagramToolVirt />}
          {active === 7 && <DiagramTrifecta />}
        </div>
      </div>
    </div>
  );
}

/* ─── Shared components ─── */
function Title({ children }) {
  return <div style={{ fontSize: 18, fontWeight: 700, color: C.bright, marginBottom: 8, textAlign: "center" }}>{children}</div>;
}
function Subtitle({ children }) {
  return <div style={{ fontSize: 12, color: C.dim, marginBottom: 28, textAlign: "center" }}>{children}</div>;
}
function Box({ children, color = C.blue, bg, width, style = {} }) {
  return (
    <div style={{
      background: bg || `${color}15`, border: `1.5px solid ${color}`,
      borderRadius: 10, padding: "14px 18px", width: width || "auto",
      textAlign: "center", ...style,
    }}>{children}</div>
  );
}
function Label({ children, color = C.bright, size = 13, bold = true }) {
  return <div style={{ fontSize: size, fontWeight: bold ? 700 : 400, color }}>{children}</div>;
}
function SmallLabel({ children, color = C.dim }) {
  return <div style={{ fontSize: 10, color, marginTop: 3, lineHeight: 1.4 }}>{children}</div>;
}
function Arrow({ vertical = false, color = C.dim, label }) {
  if (vertical) return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "6px 0" }}>
      <div style={{ width: 2, height: 24, background: color }} />
      <div style={{ color, fontSize: 16, lineHeight: 1 }}>▼</div>
      {label && <div style={{ fontSize: 9, color: C.dim, marginTop: 2 }}>{label}</div>}
    </div>
  );
  return (
    <div style={{ display: "flex", alignItems: "center", padding: "0 8px" }}>
      <div style={{ height: 2, width: 32, background: color }} />
      <div style={{ color, fontSize: 14, lineHeight: 1 }}>▶</div>
    </div>
  );
}
function VS({ left, right, leftColor = C.red, rightColor = C.green }) {
  return (
    <div style={{ display: "flex", alignItems: "stretch", gap: 24 }}>
      <div style={{ flex: 1 }}>{left}</div>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 14, fontWeight: 700, color: C.dim,
        padding: "0 8px",
      }}>vs</div>
      <div style={{ flex: 1 }}>{right}</div>
    </div>
  );
}

/* ─── 1A: The Pattern ─── */
function DiagramPattern() {
  return (
    <div>
      <Title>The Pattern: Why Every Defense Breaks</Title>
      <Subtitle>Agents process trusted and untrusted data in the same cognitive space</Subtitle>
      <VS
        left={
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <Label color={C.red}>Current Architecture</Label>
            <SmallLabel color={C.dim}>Filters after perception</SmallLabel>
            <div style={{ height: 20 }} />
            <Box color={C.orange} width={220}>
              <Label color={C.orange}>Raw Reality</Label>
              <SmallLabel>emails, docs, MCP, web</SmallLabel>
            </Box>
            <Arrow vertical color={C.orange} />
            <Box color={C.red} width={220} style={{ border: `1.5px dashed ${C.red}` }}>
              <Label color={C.red} size={11}>Guardrails / Filters</Label>
              <SmallLabel>probabilistic, bypassable</SmallLabel>
              <SmallLabel color={C.red}>90%+ bypass under adaptive attack</SmallLabel>
            </Box>
            <Arrow vertical color={C.red} />
            <Box color={C.taint} width={220}>
              <Label color={C.text}>Agent</Label>
              <SmallLabel>already perceived raw input</SmallLabel>
            </Box>
            <Arrow vertical color={C.red} />
            <Box color={C.red} width={220}>
              <Label color={C.red}>Damage</Label>
              <SmallLabel>exfiltration, corruption, misuse</SmallLabel>
            </Box>
          </div>
        }
        right={
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
            <Label color={C.green}>Agent Hypervisor</Label>
            <SmallLabel color={C.dim}>Redefines what exists</SmallLabel>
            <div style={{ height: 20 }} />
            <Box color={C.orange} width={220}>
              <Label color={C.orange}>Raw Reality</Label>
              <SmallLabel>emails, docs, MCP, web</SmallLabel>
            </Box>
            <Arrow vertical color={C.blue} />
            <Box color={C.blue} width={220}>
              <Label color={C.cyan}>Virtualization Boundary</Label>
              <SmallLabel>deterministic, testable, LLM-free</SmallLabel>
              <SmallLabel color={C.green}>same input → same decision, always</SmallLabel>
            </Box>
            <Arrow vertical color={C.green} />
            <Box color={C.green} width={220}>
              <Label color={C.green}>Virtualized World</Label>
              <SmallLabel>only defined actions exist</SmallLabel>
            </Box>
            <Arrow vertical color={C.green} />
            <Box color={C.purple} width={220}>
              <Label color={C.purple}>Agent — Free & Safe</Label>
              <SmallLabel>reasons freely inside safe world</SmallLabel>
            </Box>
          </div>
        }
      />
    </div>
  );
}

/* ─── 1B: Permission vs Ontological ─── */
function DiagramPermVsOntological() {
  return (
    <div>
      <Title>Permission Security vs Ontological Security</Title>
      <Subtitle>Not "prohibit" but "do not provide"</Subtitle>
      <VS
        left={
          <Box color={C.red} style={{ padding: 24 }}>
            <Label color={C.red}>Permission Security</Label>
            <div style={{ height: 16 }} />
            <div style={{ textAlign: "left", fontSize: 12, lineHeight: 2, color: C.text }}>
              <div>❓ <strong>Question:</strong> "Can agent X do action Y?"</div>
              <div>⚙️ <strong>Method:</strong> Runtime permission check</div>
              <div>🎲 <strong>Nature:</strong> Probabilistic</div>
              <div>🔄 <strong>Bypass:</strong> Attacker iterates until filter fails</div>
              <div>📊 <strong>Result:</strong> 90%+ bypass under adaptive attack</div>
            </div>
            <div style={{ marginTop: 16, padding: "8px 12px", background: `${C.red}20`, borderRadius: 6 }}>
              <SmallLabel color={C.red}>The action exists. The agent can formulate intent.</SmallLabel>
              <SmallLabel color={C.red}>The guard might miss the intruder.</SmallLabel>
            </div>
          </Box>
        }
        right={
          <Box color={C.green} style={{ padding: 24 }}>
            <Label color={C.green}>Ontological Security</Label>
            <div style={{ height: 16 }} />
            <div style={{ textAlign: "left", fontSize: 12, lineHeight: 2, color: C.text }}>
              <div>❓ <strong>Question:</strong> "Does action Y exist in X's universe?"</div>
              <div>⚙️ <strong>Method:</strong> Construction-time definition</div>
              <div>📐 <strong>Nature:</strong> Deterministic</div>
              <div>🧱 <strong>Bypass:</strong> Can't bypass what doesn't exist</div>
              <div>🧪 <strong>Result:</strong> Unit-testable, reproducible</div>
            </div>
            <div style={{ marginTop: 16, padding: "8px 12px", background: `${C.green}20`, borderRadius: 6 }}>
              <SmallLabel color={C.green}>The action doesn't exist. No intent possible.</SmallLabel>
              <SmallLabel color={C.green}>The room the intruder wants isn't in the building.</SmallLabel>
            </div>
          </Box>
        }
      />
      <div style={{
        marginTop: 24, padding: "12px 20px", background: C.card, borderRadius: 8,
        textAlign: "center", fontSize: 12, color: C.dim, borderLeft: `3px solid ${C.blue}`,
      }}>
        <strong style={{ color: C.cyan }}>Classical precedent:</strong> A VM cannot access physical memory — not because a rule forbids it,
        but because the MMU makes physical memory invisible. The VM is free inside its world.
      </div>
    </div>
  );
}

/* ─── 2A: AI Aikido Pipeline ─── */
function DiagramAIAikido() {
  const Step = ({ icon, title, sub, color, tag }) => (
    <Box color={color} style={{ padding: "16px 14px", flex: 1, minWidth: 140 }}>
      <div style={{ fontSize: 22, marginBottom: 6 }}>{icon}</div>
      <Label color={color} size={12}>{title}</Label>
      <SmallLabel>{sub}</SmallLabel>
      {tag && <div style={{
        marginTop: 8, padding: "3px 8px", borderRadius: 4, display: "inline-block",
        fontSize: 9, fontWeight: 700, letterSpacing: ".05em",
        background: `${color}25`, color,
      }}>{tag}</div>}
    </Box>
  );

  return (
    <div>
      <Title>AI Aikido: Stochastic Design-Time → Deterministic Runtime</Title>
      <Subtitle>The LLM creates the physics. The LLM does not govern the physics.</Subtitle>
      <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
        <Step icon="🧠" title="LLM + Human" sub="Analyze inputs, generate parsers, schemas, taint rules" color={C.purple} tag="STOCHASTIC" />
        <div style={{ display: "flex", alignItems: "center" }}><Arrow color={C.purple} /></div>
        <Step icon="📋" title="World Manifest" sub="Actions, trust, capabilities, taint rules, provenance" color={C.amber} tag="REVIEWED" />
        <div style={{ display: "flex", alignItems: "center" }}><Arrow color={C.amber} /></div>
        <Step icon="⚙️" title="Compiler" sub="Manifest → lookup tables, state machines, validators" color={C.blue} tag="NO LLM SURVIVES" />
        <div style={{ display: "flex", alignItems: "center" }}><Arrow color={C.blue} /></div>
        <Step icon="🛡️" title="Runtime" sub="Pure deterministic enforcement, same input = same output" color={C.green} tag="DETERMINISTIC" />
      </div>
      <div style={{
        marginTop: 24, display: "flex", gap: 16, justifyContent: "center",
      }}>
        {[
          { label: "Copilot → code", arrow: "parsers", color: C.purple },
          { label: "Cursor → modules", arrow: "manifests", color: C.amber },
          { label: "ChatGPT → SQL", arrow: "taint rules", color: C.blue },
        ].map((x, i) => (
          <div key={i} style={{
            fontSize: 11, color: C.dim, textAlign: "center",
            padding: "8px 14px", background: C.card, borderRadius: 6,
            borderBottom: `2px solid ${x.color}`,
          }}>
            <span style={{ color: C.text }}>{x.label}</span>
            <span style={{ color: C.dim }}> → </span>
            <span style={{ color: x.color, fontWeight: 700 }}>{x.arrow}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── 2B: Convergence ─── */
function DiagramConvergence() {
  const Card = ({ icon, title, what, pattern, color }) => (
    <Box color={color} style={{ flex: 1, padding: 16, textAlign: "left" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 20 }}>{icon}</span>
        <Label color={color} size={12}>{title}</Label>
      </div>
      <SmallLabel color={C.text}>{what}</SmallLabel>
      <div style={{ marginTop: 8, padding: "4px 8px", background: `${color}15`, borderRadius: 4 }}>
        <SmallLabel color={color}>Pattern: {pattern}</SmallLabel>
      </div>
    </Box>
  );

  return (
    <div>
      <Title>Industry Convergence: Same Pattern, Different Names</Title>
      <Subtitle>Four domains independently arriving at design-time boundaries + deterministic runtime</Subtitle>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Card icon="🛡️" title="SOC Bounded Autonomy" color={C.blue}
          what="AI handles triage autonomously. Humans approve containment at defined thresholds."
          pattern="Define boundaries upfront → enforce at runtime" />
        <Card icon="🎙️" title="Voice AI Modular Architecture" color={C.purple}
          what="Text layer between transcription and synthesis enables PII redaction, compliance scanning."
          pattern="Intervention point at perception boundary" />
        <Card icon="📦" title="Cloudflare Moltworker" color={C.cyan}
          what="Ephemeral containers. Agent's world dies when task ends. Zero persistence to pivot from."
          pattern="Define agent's universe → contain by construction" />
        <Card icon="⚖️" title="Meta's Rule of Two" color={C.green}
          what="Guardrails must live outside the LLM. Kill switches cannot depend on model behavior."
          pattern="Deterministic enforcement external to model" />
      </div>
      <div style={{
        marginTop: 20, padding: 16, background: C.card, borderRadius: 8,
        textAlign: "center", borderTop: `2px solid ${C.amber}`,
      }}>
        <Label color={C.amber} size={13}>None use the same terminology. All implement the same architecture.</Label>
        <SmallLabel color={C.dim}>Design-time boundaries → Deterministic runtime → LLM off critical path</SmallLabel>
      </div>
    </div>
  );
}

/* ─── 3A: HITL Economics ─── */
function DiagramHITLEconomics() {
  const W = 380, H = 220, PAD = 40;
  const pts = (fn, n = 40) => Array.from({ length: n }, (_, i) => {
    const x = PAD + (i / (n - 1)) * (W - 2 * PAD);
    const t = i / (n - 1);
    const y = H - PAD - fn(t) * (H - 2 * PAD);
    return `${x},${y}`;
  }).join(" ");

  return (
    <div>
      <Title>The Economics of Human-in-the-Loop</Title>
      <Subtitle>Runtime HITL = O(n). Design-Time HITL = O(log n).</Subtitle>
      <div style={{ display: "flex", justifyContent: "center" }}>
        <svg width={W} height={H} style={{ background: C.card, borderRadius: 10 }}>
          {/* axes */}
          <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke={C.border} strokeWidth={1} />
          <line x1={PAD} y1={PAD} x2={PAD} y2={H - PAD} stroke={C.border} strokeWidth={1} />
          <text x={W / 2} y={H - 8} textAnchor="middle" fill={C.dim} fontSize={10}>Runtime decisions (n)</text>
          <text x={12} y={H / 2} textAnchor="middle" fill={C.dim} fontSize={10} transform={`rotate(-90,12,${H / 2})`}>Human cost</text>
          {/* O(n) line */}
          <polyline points={pts(t => t)} fill="none" stroke={C.red} strokeWidth={2.5} />
          <text x={W - PAD - 5} y={PAD + 10} textAnchor="end" fill={C.red} fontSize={11} fontWeight={700}>O(n) Runtime HITL</text>
          {/* O(log n) curve */}
          <polyline points={pts(t => t === 0 ? 0 : Math.log(1 + t * 9) / Math.log(10) * 0.35)} fill="none" stroke={C.green} strokeWidth={2.5} />
          <text x={W - PAD - 5} y={H - PAD - 55} textAnchor="end" fill={C.green} fontSize={11} fontWeight={700}>O(log n) Design-Time HITL</text>
          {/* gap annotation */}
          <line x1={W - PAD - 60} y1={PAD + 30} x2={W - PAD - 60} y2={H - PAD - 50} stroke={C.amber} strokeWidth={1} strokeDasharray="4,3" />
          <text x={W - PAD - 55} y={(PAD + 30 + H - PAD - 50) / 2 + 4} fill={C.amber} fontSize={9} fontWeight={700}>Gap grows with scale</text>
        </svg>
      </div>
      <div style={{ display: "flex", gap: 12, marginTop: 20, justifyContent: "center" }}>
        <Box color={C.red} style={{ padding: 14, flex: 1, maxWidth: 260 }}>
          <Label color={C.red} size={11}>Runtime HITL</Label>
          <SmallLabel>Every decision costs the same</SmallLabel>
          <SmallLabel>10K alerts/day × 20 min = impossible</SmallLabel>
          <SmallLabel color={C.red}>Doesn't scale. 60% of alerts ignored.</SmallLabel>
        </Box>
        <Box color={C.green} style={{ padding: 14, flex: 1, maxWidth: 260 }}>
          <Label color={C.green} size={11}>Design-Time HITL</Label>
          <SmallLabel>One decision covers thousands of cases</SmallLabel>
          <SmallLabel>Like writing a constitution</SmallLabel>
          <SmallLabel color={C.green}>require_approval trends → 0</SmallLabel>
        </Box>
      </div>
    </div>
  );
}

/* ─── 3B: Four-Phase Cycle ─── */
function DiagramFourPhase() {
  const Phase = ({ icon, title, sub, detail, color, tag }) => (
    <Box color={color} style={{ padding: 16, flex: 1, minWidth: 0 }}>
      <div style={{ fontSize: 20, marginBottom: 4 }}>{icon}</div>
      <Label color={color} size={12}>{title}</Label>
      <div style={{
        margin: "6px 0", padding: "2px 8px", borderRadius: 4,
        background: `${color}20`, display: "inline-block",
        fontSize: 9, fontWeight: 700, color,
      }}>{tag}</div>
      <SmallLabel>{sub}</SmallLabel>
      <SmallLabel color={C.dim}>{detail}</SmallLabel>
    </Box>
  );

  return (
    <div>
      <Title>The Four-Phase Cycle</Title>
      <Subtitle>Each iteration expands deterministic coverage. Exception rate trends → zero.</Subtitle>
      <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
        <Phase icon="📝" title="Design" color={C.purple} tag="HUMAN + LLM"
          sub="Co-create World Manifest" detail="Action schemas, trust policies, taint rules" />
        <div style={{ display: "flex", alignItems: "center" }}><Arrow color={C.purple} /></div>
        <Phase icon="⚙️" title="Compile" color={C.blue} tag="NO LLM SURVIVES"
          sub="Manifest → deterministic artifacts" detail="Policy tables, validators, taint matrices" />
        <div style={{ display: "flex", alignItems: "center" }}><Arrow color={C.blue} /></div>
        <Phase icon="🚀" title="Deploy" color={C.green} tag="PURELY DETERMINISTIC"
          sub="Runtime enforcement" detail="No LLM, no human, reproducible" />
        <div style={{ display: "flex", alignItems: "center" }}><Arrow color={C.green} /></div>
        <Phase icon="📊" title="Learn" color={C.amber} tag="LOGS & PATTERNS"
          sub="Escalation patterns emerge" detail="Coverage gaps become visible" />
      </div>
      {/* Feedback arrow */}
      <div style={{
        margin: "12px auto 0", width: "90%", display: "flex", alignItems: "center",
        justifyContent: "center", gap: 8,
      }}>
        <div style={{
          flex: 1, height: 2, background: `linear-gradient(to left, ${C.amber}, ${C.purple})`,
          borderRadius: 1,
        }} />
        <div style={{
          padding: "6px 16px", background: C.card, borderRadius: 6,
          border: `1px solid ${C.amber}`, fontSize: 11, color: C.amber, fontWeight: 700,
        }}>
          ← REDESIGN: Human reviews patterns, LLM re-generates, coverage expands →
        </div>
        <div style={{
          flex: 1, height: 2, background: `linear-gradient(to right, ${C.amber}, ${C.purple})`,
          borderRadius: 1,
        }} />
      </div>
    </div>
  );
}

/* ─── 4A: Tool Virtualization ─── */
function DiagramToolVirt() {
  return (
    <div>
      <Title>Tool Virtualization: MCP Through the Hypervisor</Title>
      <Subtitle>Tools connect to the hypervisor, not to the agent</Subtitle>
      <VS
        left={
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <Label color={C.red} size={13}>Current: Direct Connection</Label>
            <div style={{ height: 8 }} />
            <Box color={C.purple} width={180}><Label color={C.purple}>Agent</Label></Box>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 2, height: 20, background: C.red }} />
            </div>
            <div style={{ fontSize: 9, color: C.red, fontWeight: 700, padding: "2px 8px", background: `${C.red}15`, borderRadius: 4 }}>
              direct, unmediated
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 2, height: 20, background: C.red }} />
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "center" }}>
              {["Email", "Slack", "JIRA", "Shell", "DB"].map(t => (
                <Box key={t} color={C.orange} style={{ padding: "6px 10px" }}>
                  <SmallLabel color={C.orange}>{t}</SmallLabel>
                </Box>
              ))}
            </div>
            <div style={{ marginTop: 10, padding: "6px 12px", background: `${C.red}15`, borderRadius: 6 }}>
              <SmallLabel color={C.red}>Compromised tool = full blast radius</SmallLabel>
              <SmallLabel color={C.red}>43% command injection in MCP implementations</SmallLabel>
            </div>
          </div>
        }
        right={
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <Label color={C.green} size={13}>Hypervisor: Virtualized Devices</Label>
            <div style={{ height: 8 }} />
            <Box color={C.purple} width={180}><Label color={C.purple}>Agent</Label><SmallLabel>proposes intents only</SmallLabel></Box>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 2, height: 12, background: C.green }} />
            </div>
            <Box color={C.blue} width={240}>
              <Label color={C.cyan} size={12}>Hypervisor</Label>
              <SmallLabel>schema validation · capability check</SmallLabel>
              <SmallLabel>taint enforcement · provenance tracking</SmallLabel>
            </Box>
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 2, height: 12, background: C.green }} />
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "center" }}>
              {["Email", "Slack", "JIRA", "Shell", "DB"].map(t => (
                <Box key={t} color={C.green} style={{ padding: "6px 10px" }}>
                  <SmallLabel color={C.green}>{t}</SmallLabel>
                </Box>
              ))}
            </div>
            <div style={{ marginTop: 10, padding: "6px 12px", background: `${C.green}15`, borderRadius: 6 }}>
              <SmallLabel color={C.green}>Undefined tool doesn't exist (not forbidden)</SmallLabel>
              <SmallLabel color={C.green}>Adding tool doesn't change agent or architecture</SmallLabel>
            </div>
          </div>
        }
      />
    </div>
  );
}

/* ─── 4B: Lethal Trifecta ─── */
function DiagramTrifecta() {
  const Leg = ({ icon, title, threat, defense, defIcon, color }) => (
    <Box color={color} style={{ padding: 16, flex: 1, textAlign: "left" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 22 }}>{icon}</span>
        <Label color={color} size={12}>{title}</Label>
      </div>
      <div style={{ padding: "6px 10px", background: `${C.red}12`, borderRadius: 6, marginBottom: 10 }}>
        <SmallLabel color={C.red}>Threat: {threat}</SmallLabel>
      </div>
      <div style={{ padding: "6px 10px", background: `${color}15`, borderRadius: 6, display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 14 }}>{defIcon}</span>
        <SmallLabel color={color}>{defense}</SmallLabel>
      </div>
    </Box>
  );

  return (
    <div>
      <Title>Breaking the Lethal Trifecta</Title>
      <Subtitle>Three independent mechanisms — even if one is imperfect, the others contain the blast radius</Subtitle>
      <div style={{ textAlign: "center", marginBottom: 20 }}>
        <span style={{
          padding: "6px 16px", background: `${C.red}20`, borderRadius: 6,
          fontSize: 11, color: C.red, fontWeight: 700,
        }}>
          Simon Willison's "Lethal Trifecta": private data + untrusted content + external comms = exploitation
        </span>
      </div>
      <div style={{ display: "flex", gap: 12 }}>
        <Leg icon="🔒" title="Private Data Access" color={C.blue}
          threat="Agent has default access to all connected data"
          defense="Provenance-gated access. Capability matrix per trust level. Data carries origin chain."
          defIcon="🧬" />
        <Leg icon="📨" title="Untrusted Content" color={C.purple}
          threat="Raw input enters agent's cognitive space"
          defense="Input Virtualization. Structured semantic events with source + trust + sanitized payload."
          defIcon="🛡️" />
        <Leg icon="📡" title="External Communication" color={C.cyan}
          threat="Agent can send data to external endpoints"
          defense="TaintContainmentLaw. Tainted data cannot cross external boundary — by construction."
          defIcon="⚛️" />
      </div>
      <div style={{
        marginTop: 20, padding: 14, background: C.card, borderRadius: 8,
        textAlign: "center", borderTop: `2px solid ${C.green}`,
      }}>
        <Label color={C.green} size={13}>Defense in depth through orthogonal boundaries</Label>
        <SmallLabel color={C.dim}>Not one perfect wall — three independent physics laws governing three independent properties</SmallLabel>
      </div>
    </div>
  );
}
