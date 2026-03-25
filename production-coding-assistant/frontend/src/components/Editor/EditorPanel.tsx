import { useEffect, useRef, useState } from "react";
import MonacoEditor from "@monaco-editor/react";
import { X, ChevronRight } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { motion, AnimatePresence } from "framer-motion";

export default function EditorPanel() {
  const { tabs, activeFileId, removeTab, setActiveTab, updateTab } = useAppStore();
  const [editorValue, setEditorValue] = useState("");
  const editorRef = useRef<unknown>(null);
  const activeTab = tabs.find((t) => t.id === activeFileId);

  useEffect(() => {
    setEditorValue(activeTab?.content ?? "");
  }, [activeTab?.id]);

  /* ── Empty state ─────────────────────────────────────────────── */
  if (tabs.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-[#09090b] select-none text-zinc-500 relative z-0">
        <div className="text-[64px] opacity-5 font-mono font-bold tracking-tighter text-zinc-100 mb-6 drop-shadow-2xl">
          &lt;/&gt;
        </div>
        <div className="text-sm text-zinc-400 font-medium tracking-wide">
          Production AI Assistant
        </div>
        <div className="text-xs text-zinc-600 text-center mt-2 leading-relaxed max-w-[250px]">
          Open a file from the Explorer or ask the AI to generate one.
        </div>
        <div className="mt-12 flex flex-col gap-3 text-[11px] font-mono opacity-60">
          <span className="flex items-center gap-3 justify-between w-48">
            <span className="flex gap-1.5"><kbd className="bg-zinc-800 border border-zinc-700 rounded px-1.5 shadow-inner">Ctrl</kbd> <kbd className="bg-zinc-800 border border-zinc-700 rounded px-1.5 shadow-inner">P</kbd></span>
            <span className="text-zinc-400">Go to file</span>
          </span>
          <span className="flex items-center gap-3 justify-between w-48">
            <span className="flex gap-1.5"><kbd className="bg-zinc-800 border border-zinc-700 rounded px-1.5 shadow-inner">Ctrl</kbd> <kbd className="bg-zinc-800 border border-zinc-700 rounded px-1.5 shadow-inner">Enter</kbd></span>
            <span className="text-zinc-400">Send to AI</span>
          </span>
        </div>
      </div>
    );
  }

  /* ── Breadcrumb segments ─────────────────────────────────────── */
  const pathParts = activeTab?.path.replace(/\\/g, "/").split("/") ?? [];

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-[#09090b] z-0 overflow-hidden relative">
      {/* Tab bar */}
      <div className="flex items-end h-[38px] bg-[#121214] border-b border-[#27272a] overflow-x-auto overflow-y-hidden shrink-0 [&::-webkit-scrollbar]:h-0">
        <AnimatePresence initial={false}>
          {tabs.map((tab) => {
            const active = tab.id === activeFileId;
            return (
              <motion.div
                layout
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                key={tab.id}
                className={`group flex items-center gap-2 h-full px-3 text-[13px] border-r border-[#27272a] cursor-pointer whitespace-nowrap shrink-0 relative transition-colors ${
                  active ? "bg-[#09090b] text-zinc-100" : "bg-[#121214] text-zinc-500 hover:bg-[#1f1f22] hover:text-zinc-300"
                }`}
                onClick={() => setActiveTab(tab.id)}
                title={tab.path}
              >
                {active && (
                  <motion.div
                    layoutId="activeTabIndicator"
                    className="absolute top-0 left-0 right-0 h-[2px] bg-blue-500"
                  />
                )}
                
                {tab.isDirty ? <span className="w-2 h-2 rounded-full bg-zinc-300 shrink-0" /> : null}
                
                <span className="font-sans font-medium">{tab.name}</span>
                
                <button
                  className={`w-4 h-4 flex items-center justify-center rounded transition-all ml-1 ${
                    active ? "opacity-100 text-zinc-400 hover:bg-zinc-800 hover:text-white" : "opacity-0 group-hover:opacity-100 text-zinc-500 hover:bg-zinc-700 hover:text-zinc-200"
                  }`}
                  onClick={(e) => { e.stopPropagation(); removeTab(tab.id); }}
                >
                  <X size={13} strokeWidth={2.5} />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* Breadcrumb */}
      {activeTab && (
        <div className="flex items-center h-7 px-4 bg-[#09090b] border-b border-[#1c1c1f] text-xs text-zinc-500 shrink-0 gap-1.5 shadow-sm">
          {pathParts.map((part, i) => (
            <span key={i} className="flex items-center gap-1.5">
              {i > 0 && <ChevronRight size={12} className="text-zinc-700 stroke-[2.5px]" />}
              <span className={`font-medium ${i === pathParts.length - 1 ? "text-zinc-300" : "text-zinc-500"}`}>
                {part}
              </span>
            </span>
          ))}
        </div>
      )}

      {/* Monaco editor */}
      {activeTab && (
        <div className="flex-1 overflow-hidden relative min-h-0 bg-[#09090b]">
          <MonacoEditor
            height="100%"
            language={activeTab.language}
            value={editorValue}
            onChange={(val) => {
              if (val === undefined || !activeFileId) return;
              setEditorValue(val);
              updateTab(activeFileId, { content: val, isDirty: val !== activeTab.content });
            }}
            onMount={(editor) => { editorRef.current = editor; }}
            theme="vs-dark"
            path={activeTab.path}
            options={{
              minimap: { enabled: true, scale: 0.75 },
              fontSize: 13,
              lineHeight: 22,
              fontFamily: 'JetBrains Mono, Fira Code, Consolas, monospace',
              fontLigatures: true,
              scrollBeyondLastLine: false,
              automaticLayout: true,
              colorDecorators: true,
              cursorBlinking: "smooth",
              cursorStyle: "line",
              smoothScrolling: true,
              bracketPairColorization: { enabled: true },
              guides: { bracketPairs: true, indentation: true },
              renderLineHighlight: "all",
              lineNumbers: "on",
              glyphMargin: false,
              folding: true,
              wordWrap: "off",
              padding: { top: 16, bottom: 24 },
              suggestFontSize: 12,
              tabSize: 2,
            }}
          />
        </div>
      )}
    </div>
  );
}
