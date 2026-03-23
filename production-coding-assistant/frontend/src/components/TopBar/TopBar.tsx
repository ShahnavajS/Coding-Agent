import { GitBranch, Save, Settings2, Bell } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { fileAPI } from "../../utils/api";

export default function TopBar() {
  const {
    toggleSettings,
    tabs,
    activeFileId,
    updateTab,
    setDiffViewer,
    setStatusText,
    statusText,
    currentBranch,
    settings,
  } = useAppStore();

  const activeTab = tabs.find((t) => t.id === activeFileId);

  const handleSave = async () => {
    if (!activeTab) { setStatusText("No file selected"); return; }
    try {
      const preview = await fileAPI.previewWrite(activeTab.path, activeTab.content);
      setDiffViewer({
        isOpen: true,
        diffId: preview.id,
        fileName: preview.path,
        originalContent: preview.originalContent,
        modifiedContent: preview.modifiedContent,
        validation: preview.validation,
        onAccept: async () => {
          const result = await fileAPI.applyDiff(preview.id);
          updateTab(activeTab.id, { isDirty: false });
          setStatusText(`Saved · checkpoint ${result.checkpoint.id.slice(0, 8)}`);
        },
        onReject: () => setStatusText(`Save cancelled for ${preview.path}`),
      });
      setStatusText(`Preview ready · ${preview.path}`);
    } catch (err) {
      setStatusText(`Save failed: ${err instanceof Error ? err.message : "Unknown"}`);
    }
  };

  return (
    <div className="titlebar" style={{ WebkitAppRegion: "drag" } as React.CSSProperties}>
      {/* Left: app name + provider badge */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, WebkitAppRegion: "no-drag" } as React.CSSProperties}>
        <span style={{
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          color: "var(--text-primary)",
          fontWeight: 600,
          letterSpacing: 1,
        }}>
          Production Coding Assistant
        </span>
        <span style={{
          fontSize: 11,
          color: "var(--text-inactive)",
          background: "rgba(255,255,255,0.06)",
          border: "1px solid var(--border)",
          borderRadius: 3,
          padding: "1px 6px",
        }}>
          {settings?.defaultProvider || "groq"}
        </span>
      </div>

      {/* Centre: status text */}
      <div style={{
        flex: 1,
        textAlign: "center",
        fontSize: 11,
        color: "var(--text-inactive)",
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        padding: "0 24px",
        WebkitAppRegion: "drag",
      } as React.CSSProperties}>
        {statusText}
      </div>

      {/* Right: actions */}
      <div style={{ display: "flex", alignItems: "center", gap: 4, WebkitAppRegion: "no-drag" } as React.CSSProperties}>
        <button
          onClick={() => void handleSave()}
          className="btn-secondary"
          style={{ height: 22, padding: "0 8px", fontSize: 11, gap: 4 }}
          title="Preview & save"
        >
          <Save size={12} />
          Save
        </button>

        <div style={{ width: 1, height: 14, background: "var(--border)", margin: "0 4px" }} />

        <div
          style={{
            display: "flex", alignItems: "center", gap: 4,
            fontSize: 11, color: "var(--text-secondary)",
            cursor: "pointer", padding: "2px 6px", borderRadius: 3, transition: "background 0.1s",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "")}
        >
          <GitBranch size={12} />
          <span>{currentBranch || "workspace"}</span>
        </div>

        <button
          onClick={toggleSettings}
          className="icon-btn"
          style={{ width: 24, height: 24 }}
          title="Settings"
        >
          <Settings2 size={14} strokeWidth={1.5} />
        </button>

        <button className="icon-btn" style={{ width: 24, height: 24 }} title="Notifications">
          <Bell size={14} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}
