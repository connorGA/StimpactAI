"use client";

import { useId } from "react";

type DiffLineStyle = "headerMinus" | "headerPlus" | "hunk" | "add" | "remove" | "context" | "meta";

function classifyLine(line: string): { style: DiffLineStyle; body: string } {
  if (line.startsWith("+++ ")) {
    return { style: "headerPlus", body: line };
  }
  if (line.startsWith("--- ")) {
    return { style: "headerMinus", body: line };
  }
  if (line.startsWith("@@") && line.includes("@@", 1)) {
    return { style: "hunk", body: line };
  }
  if (
    line.startsWith("diff --git") ||
    line.startsWith("index ") ||
    line.startsWith("old mode") ||
    line.startsWith("new mode") ||
    line.startsWith("new file mode") ||
    line.startsWith("deleted file mode") ||
    line.startsWith("similarity index") ||
    line.startsWith("Binary files") ||
    line.startsWith("rename from") ||
    line.startsWith("rename to")
  ) {
    return { style: "meta", body: line };
  }
  if (line.startsWith("\\")) {
    return { style: "meta", body: line };
  }
  if (line.startsWith("+")) {
    return { style: "add", body: line.slice(1) };
  }
  if (line.startsWith("-")) {
    return { style: "remove", body: line.slice(1) };
  }
  if (line.length === 0) {
    return { style: "context", body: "" };
  }
  if (line[0] === " ") {
    return { style: "context", body: line.slice(1) };
  }
  return { style: "context", body: line };
}

function rowClasses(style: DiffLineStyle): { tr: string; text: string } {
  switch (style) {
    case "add":
      return {
        tr: "bg-[rgba(34,197,94,0.1)]",
        text: "text-[#a7f3d0]",
      };
    case "remove":
      return {
        tr: "bg-[rgba(248,113,113,0.09)]",
        text: "text-[#fecdd3]",
      };
    case "hunk":
      return {
        tr: "bg-[rgba(45,127,249,0.1)]",
        text: "text-[#c4d4ff]",
      };
    case "headerMinus":
    case "headerPlus":
      return {
        tr: "bg-white/[0.05]",
        text: "text-white/70",
      };
    case "meta":
      return {
        tr: "bg-black/25",
        text: "text-white/50",
      };
    default:
      return {
        tr: "bg-transparent",
        text: "text-white/65",
      };
  }
}

function prefixFor(style: DiffLineStyle): string {
  if (style === "add") return "+";
  if (style === "remove") return "−";
  if (style === "context") return " ";
  return "";
}

/**
 * Splits a unified diff on file-pair headers (`--- a/...` + `+++ b/...`).
 */
export function splitUnifiedDiffByFile(
  diff: string,
): { id: string; path: string; content: string }[] {
  const text = diff.trim();
  if (!text) {
    return [];
  }
  const lines = text.split("\n");
  const blocks: { id: string; path: string; content: string }[] = [];
  let i = 0;

  const makeId = (p: string, n: number) =>
    `diff-${n}-${p.replace(/[^a-zA-Z0-9._/-]+/g, "-").replace(/^-|-$/g, "") || "file"}`;

  while (i < lines.length) {
    if (lines[i].startsWith("--- ")) {
      const start = i;
      const plusLine = lines[i + 1] ?? "";
      let path = "file";
      const plusMatch = plusLine.match(/^\+\+\+ [ab]\/(.+)$/);
      if (plusMatch) {
        path = plusMatch[1].trim();
      } else {
        const minusMatch = lines[i].match(/^--- [ab]\/(.+)$/);
        if (minusMatch) {
          path = minusMatch[1].trim();
        } else if (lines[i].includes("dev/null")) {
          path = "new or deleted file";
        }
      }
      i += 2;
      while (i < lines.length && !lines[i].startsWith("--- ")) {
        i++;
      }
      const content = lines.slice(start, i).join("\n");
      blocks.push({
        id: makeId(path, blocks.length),
        path,
        content,
      });
    } else {
      const start = i;
      while (i < lines.length && !lines[i].startsWith("--- ")) {
        i++;
      }
      const chunk = lines.slice(start, i).join("\n");
      if (chunk.trim()) {
        blocks.push({
          id: `preamble-${blocks.length}`,
          path: "Preamble",
          content: chunk,
        });
      }
    }
  }

  if (blocks.length === 0) {
    return [{ id: "diff-all", path: "Patch", content: text }];
  }
  return blocks;
}

type UnifiedDiffViewProps = {
  diff: string;
  className?: string;
  /** Split into one card per file when diff contains standard `---` / `+++` headers. */
  splitByFile?: boolean;
};

export function UnifiedDiffView({ diff, className = "", splitByFile = true }: UnifiedDiffViewProps) {
  const baseId = useId();
  if (!diff.trim()) {
    return <p className="text-sm text-white/45">No diff available.</p>;
  }

  const canSplit = diff.includes("--- a/") || diff.includes("--- b/") || /^\+\+\+ [ab]\//m.test(diff);
  const blocks =
    splitByFile && canSplit ? splitUnifiedDiffByFile(diff) : [{ id: "single", path: "Changes", content: diff }];

  if (blocks.length > 1) {
    return (
      <div className={`space-y-4 ${className}`.trim()}>
        {blocks.map((block, index) => (
          <FileDiffTable
            key={`${baseId}-${block.id}-${String(index)}`}
            anchorId={block.id}
            filePath={block.path}
            content={block.content}
          />
        ))}
      </div>
    );
  }

  return (
    <div className={className}>
      <FileDiffTable filePath={blocks[0]?.path ?? "Changes"} content={diff} />
    </div>
  );
}

type FileDiffTableProps = {
  filePath: string;
  content: string;
  anchorId?: string;
};

function FileDiffTable({ filePath, content, anchorId }: FileDiffTableProps) {
  const lines = content.split("\n");
  return (
    <div
      id={anchorId}
      className="scroll-mt-24 overflow-hidden rounded-xl border border-white/[0.08] bg-[#0a0c10] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
    >
      <div className="flex items-center justify-between gap-2 border-b border-white/[0.08] bg-white/[0.04] px-3 py-2.5">
        <p className="min-w-0 truncate font-mono text-[12px] font-medium text-white/90">{filePath}</p>
        <span className="shrink-0 text-[10px] font-medium uppercase tracking-wide text-white/35">diff</span>
      </div>
      <div className="max-h-[min(70vh,48rem)] overflow-auto">
        <table className="w-full min-w-0 table-fixed border-collapse font-mono text-[11px] leading-relaxed sm:text-[12px]">
          <tbody>
            {lines.map((line, index) => {
              const { style, body } = classifyLine(line);
              const { tr, text } = rowClasses(style);
              const showPrefix = style === "add" || style === "remove" || style === "context";
              return (
                <tr key={`${String(index)}-${line.slice(0, 20)}`} className={tr}>
                  <td className="w-8 select-none border-b border-white/[0.04] py-0.5 pr-0 pl-2 text-right align-top text-[10px] text-white/30">
                    {index + 1}
                  </td>
                  <td className="w-5 select-none border-b border-white/[0.04] py-0.5 text-center align-top font-bold text-white/35">
                    {showPrefix ? (
                      <span
                        className={
                          style === "add"
                            ? "text-[#4ade80]"
                            : style === "remove"
                              ? "text-[#f87171]"
                              : "text-white/20"
                        }
                      >
                        {style === "context" ? "\u00A0" : prefixFor(style) || "·"}
                      </span>
                    ) : null}
                  </td>
                  <td className={`border-b border-white/[0.04] py-0.5 pr-2 pl-0 align-top ${text}`}>
                    <code className="whitespace-pre-wrap break-all">
                      {showPrefix ? body : line}
                    </code>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
