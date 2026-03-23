import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { DiffEditor } from "@monaco-editor/react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, FileCode2, GitCommitHorizontal, X } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";

function lineCount(value: string): number {
  return value === "" ? 0 : value.split("\n").length;
}

export default function DiffViewer() {
  const { diffViewer, setDiffViewer, setStatusText } = useAppStore();
  const [isApplying, setIsApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  const metrics = useMemo(() => {
    if (!diffViewer) return null;
    const before = lineCount(diffViewer.originalContent);
    const after = lineCount(diffViewer.modifiedContent);
    return {
      before,
      after,
      delta: after - before,
    };
  }, [diffViewer]);

  if (!diffViewer || !metrics) return null;

  return createPortal(
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[9998] flex items-center justify-center bg-black/70 p-3 backdrop-blur-sm"
        onClick={() => setDiffViewer(null)}
      >
        <motion.div
          initial={{ scale: 0.98, y: 16 }}
          animate={{ scale: 1, y: 0 }}
          exit={{ scale: 0.98, y: 16 }}
          transition={{ type: "spring", stiffness: 240, damping: 24 }}
          onClick={(event) => event.stopPropagation()}
          className="flex h-[90vh] w-full max-w-[92rem] flex-col overflow-hidden rounded-xl border border-dark-border bg-dark-surface shadow-2xl"
        >
          <div className="flex items-center justify-between border-b border-dark-border px-5 py-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-gray-100">
                <FileCode2 size={16} className="text-accent-blue" />
                <h2 className="font-mono text-base">Review Changes</h2>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-gray-400">
                <span className="font-mono text-gray-200">{diffViewer.fileName}</span>
                <span>language: {diffViewer.validation?.language || "text"}</span>
                <span>
                  lines: {metrics.before} {"->"} {metrics.after}
                </span>
                <span
                  className={
                    metrics.delta >= 0 ? "text-accent-green" : "text-accent-red"
                  }
                >
                  {metrics.delta >= 0 ? "+" : ""}
                  {metrics.delta} lines
                </span>
                {diffViewer.validation && (
                  <span
                    className={
                      diffViewer.validation.ok
                        ? "text-accent-green"
                        : "text-accent-red"
                    }
                  >
                    {diffViewer.validation.ok ? "validation passed" : "validation failed"}
                  </span>
                )}
              </div>
            </div>

            <button
              onClick={() => setDiffViewer(null)}
              className="rounded-sm p-2 transition-colors hover:bg-dark-hover"
            >
              <X size={18} className="text-gray-400" />
            </button>
          </div>

          <div className="border-b border-dark-border bg-dark-bg/60 px-5 py-3 text-xs text-gray-400">
            <div className="flex items-center gap-2">
              <GitCommitHorizontal size={14} className="text-accent-blue" />
              <span>Apply this diff to write the file into the workspace.</span>
            </div>
            {diffViewer.validation && diffViewer.validation.messages.length > 0 && (
              <div className="mt-2 space-y-1">
                {diffViewer.validation.messages.map((message) => (
                  <div key={message}>{message}</div>
                ))}
              </div>
            )}
            {applyError && <div className="mt-2 text-accent-red">{applyError}</div>}
          </div>

          <div className="min-h-0 flex-1 bg-[#11151c]">
            <DiffEditor
              height="100%"
              original={diffViewer.originalContent}
              modified={diffViewer.modifiedContent}
              language={diffViewer.validation?.language || "text"}
              theme="vs-dark"
              options={{
                renderSideBySide: true,
                readOnly: true,
                automaticLayout: true,
                scrollBeyondLastLine: false,
                minimap: { enabled: false },
                fontSize: 13,
                fontFamily:
                  '"SFMono-Regular", "Menlo", "Monaco", "Cascadia Mono", monospace',
                lineNumbers: "on",
                wordWrap: "on",
                diffWordWrap: "on",
                renderOverviewRuler: true,
              }}
            />
          </div>

          <div className="flex items-center justify-between border-t border-dark-border px-5 py-4">
            <div className="text-xs text-gray-500">
              Review like VS Code: compare, validate, then accept or reject.
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  diffViewer.onReject?.();
                  setDiffViewer(null);
                }}
                className="button-secondary flex items-center gap-2"
                disabled={isApplying}
              >
                <X size={14} />
                Reject
              </button>
              <button
                onClick={async () => {
                  try {
                    setApplyError(null);
                    setIsApplying(true);
                    await diffViewer.onAccept?.();
                    setStatusText(`Applied ${diffViewer.fileName}`);
                    setDiffViewer(null);
                  } catch (error) {
                    const message =
                      error instanceof Error ? error.message : "Failed to apply diff";
                    setApplyError(message);
                    setStatusText(`Apply failed: ${message}`);
                  } finally {
                    setIsApplying(false);
                  }
                }}
                className="button-primary flex items-center gap-2"
                disabled={isApplying || (diffViewer.validation ? !diffViewer.validation.ok : false)}
              >
                <Check size={14} />
                {isApplying ? "Applying..." : "Apply Changes"}
              </button>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body
  );
}
