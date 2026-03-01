import type { Source } from "@/lib/api";

interface Props {
  source: Source;
  index: number;
}

export default function SourceCard({ source, index }: Props) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
      <div className="font-medium text-slate-700">
        [{index + 1}] {source.doc_number ?? "Unknown"} — p.{source.page_number}
      </div>
      {source.title && (
        <div className="mt-0.5 truncate text-slate-500">{source.title}</div>
      )}
      <div className="mt-0.5 truncate font-mono text-slate-400">{source.s3_key}</div>
    </div>
  );
}
