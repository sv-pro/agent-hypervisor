interface RuleCardProps {
  rule: string;
  decision: string;
  reason: string;
}

export function RuleCard({ rule, decision, reason }: RuleCardProps) {
  const isDeny = decision === 'deny';
  const isSimulate = decision === 'simulate';

  return (
    <div className={`mt-2 rounded-lg p-2 ${isDeny ? 'animate-rule-glow' : ''}`}
      style={{
        background: isDeny
          ? 'rgba(245,158,11,0.08)'
          : isSimulate
          ? 'rgba(99,102,241,0.08)'
          : 'rgba(16,185,129,0.08)',
      }}
    >
      <div className="flex items-center gap-2">
        <span className={`text-xs font-bold ${
          isDeny ? 'text-amber' : isSimulate ? 'text-sim' : 'text-green'
        }`}>
          {rule}
        </span>
        <span className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded ${
          isDeny ? 'bg-deny/20 text-deny' : isSimulate ? 'bg-sim/20 text-sim' : 'bg-green/20 text-green'
        }`}>
          {decision}
        </span>
      </div>
      <div className="text-[10px] text-muted mt-1 leading-relaxed">{reason}</div>
    </div>
  );
}
