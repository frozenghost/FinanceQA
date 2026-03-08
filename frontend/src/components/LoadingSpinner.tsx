interface Props {
  label?: string;
}

export function LoadingSpinner({ label }: Props) {
  return (
    <div className="flex gap-2 items-center text-slate-400">
      <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" />
      <div
        className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce"
        style={{ animationDelay: "150ms" }}
      />
      <div
        className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce"
        style={{ animationDelay: "300ms" }}
      />
      {label && <span className="ml-2 text-sm">{label}</span>}
    </div>
  );
}
