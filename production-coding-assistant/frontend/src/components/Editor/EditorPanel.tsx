import { useEffect, useRef, useState } from "react";
import MonacoEditor from "@monaco-editor/react";
import { X } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";

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
      <div className="editor-area editor-empty" style={{ flex: 1 }}>
        <div className="editor-empty-logo">&lt;/&gt;</div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          Production Coding Assistant
        </div>
        <div className="editor-empty-hint">
          Open a file from the Explorer<br />
          or ask the AI to create one
        </div>
        <div style={{
          marginTop: 12,
          display: "flex",
          flexDirection: "column",
          gap: 4,
          color: "var(--text-inactive)",
          fontSize: 11,
          fontFamily: "var(--font-mono)",
        }}>
          <span><kbd>Ctrl</kbd> <kbd>P</kbd> &nbsp;Go to file</span>
          <span><kbd>Ctrl</kbd> <kbd>Enter</kbd> &nbsp;Send to AI</span>
        </div>
      </div>
    );
  }

  /* ── Breadcrumb segments ─────────────────────────────────────── */
  const pathParts = activeTab?.path.replace(/\\/g, "/").split("/") ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
      {/* Tab bar */}
      <div className="tab-bar">
        {tabs.map((tab) => {
          const active = tab.id === activeFileId;
          return (
            <div
              key={tab.id}
              className={`tab${active ? " active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
              title={tab.path}
            >
              {tab.isDirty
                ? <span className="tab-dirty" />
                : null
              }
              <span style={{ fontSize: 13, fontFamily: "var(--font-ui)" }}>{tab.name}</span>
              <button
                className="tab-close"
                onClick={(e) => { e.stopPropagation(); removeTab(tab.id); }}
              >
                <X size={12} />
              </button>
            </div>
          );
        })}
      </div>

      {/* Breadcrumb */}
      {activeTab && (
        <div className="breadcrumb">
          {pathParts.map((part, i) => (
            <span key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              {i > 0 && <span className="breadcrumb-sep">›</span>}
              <span style={{
                color: i === pathParts.length - 1 ? "var(--text-primary)" : "var(--text-secondary)",
              }}>
                {part}
              </span>
            </span>
          ))}
        </div>
      )}

      {/* Monaco editor */}
      {activeTab && (
        <div className="editor-area" style={{ flex: 1 }}>
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
              minimap: { enabled: true, scale: 1 },
              fontSize: 13,
              lineHeight: 20,
              fontFamily: '"Cascadia Code", "Fira Code", "Consolas", monospace',
              fontLigatures: true,
              scrollBeyondLastLine: false,
              automaticLayout: true,
              colorDecorators: true,
              cursorBlinking: "smooth",
              cursorStyle: "line",
              smoothScrolling: true,
              bracketPairColorization: { enabled: true },
              guides: { bracketPairs: true, indentation: true },
              renderLineHighlight: "line",
              lineNumbers: "on",
              glyphMargin: false,
              folding: true,
              wordWrap: "off",
              padding: { top: 8, bottom: 8 },
              suggestFontSize: 12,
              tabSize: 2,
            }}
          />
        </div>
      )}
    </div>
  );
}
