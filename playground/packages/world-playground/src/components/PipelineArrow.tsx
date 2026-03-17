interface Props {
  active?: boolean;
  label?: string;
}

export function PipelineArrow({ active = true, label }: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 flex-shrink-0 w-6 select-none">
      <div className={`h-px flex-1 w-full ${active ? 'bg-border-bright' : 'bg-border/40'}`} />
      <div className={`text-[10px] ${active ? 'text-subtle' : 'text-dim'}`}>▶</div>
      {label && (
        <span className="text-[8px] text-muted/40 font-mono rotate-90 whitespace-nowrap">{label}</span>
      )}
      <div className={`h-px flex-1 w-full ${active ? 'bg-border-bright' : 'bg-border/40'}`} />
    </div>
  );
}
