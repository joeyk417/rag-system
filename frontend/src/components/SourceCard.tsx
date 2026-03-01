import type { Source } from "@/lib/api";

interface Props {
  source: Source;
  index: number;
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const colour =
    pct >= 80
      ? "bg-green-100 text-green-700 border-green-200"
      : pct >= 60
        ? "bg-yellow-100 text-yellow-700 border-yellow-200"
        : "bg-red-100 text-red-600 border-red-200";
  return (
    <span
      className={`ml-auto flex-shrink-0 rounded-full border px-2 py-0.5 text-xs font-semibold ${colour}`}
      title="Relevance score (cosine similarity)"
    >
      {pct}%
    </span>
  );
}

export default function SourceCard({ source, index }: Props) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
      <div className="flex items-start gap-1">
        <span className="font-medium text-slate-700">
          [{index + 1}] {source.doc_number ?? "Unknown"} — p.{source.page_number}
        </span>
        {source.score !== null && source.score !== undefined && (
          <ScoreBadge score={source.score} />
        )}
      </div>
      {source.title && (
        <div className="mt-0.5 truncate text-slate-500">{source.title}</div>
      )}
      <div className="mt-0.5 truncate font-mono text-slate-400">{source.s3_key}</div>
    </div>
  );
}
