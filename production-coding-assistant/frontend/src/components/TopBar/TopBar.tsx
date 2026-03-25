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
    <div 
      className="flex items-center h-10 shrink-0 bg-[#18181b]/90 backdrop-blur-md border-b border-zinc-800/80 px-4 gap-4 select-none"
      style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
    >
      {/* Left: app name + provider badge */}
      <div 
        className="flex items-center gap-3 shrink-0" 
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        <span className="font-mono text-[13px] font-semibold text-zinc-200 tracking-wide drop-shadow-sm">
          Production AI Assistant
        </span>
        <span className="px-2 py-0.5 text-[10px] uppercase tracking-wider font-bold rounded-full border border-zinc-700 bg-zinc-800/60 text-teal-400">
          {settings?.defaultProvider || "groq"}
        </span>
      </div>

      {/* Centre: status text */}
      <div 
        className="flex-1 text-center text-xs text-zinc-500 font-medium truncate px-6 uppercase tracking-widest drop-shadow-[0_1px_1px_rgba(0,0,0,0.8)]"
        style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
      >
        {statusText}
      </div>

      {/* Right: actions */}
      <div 
        className="flex items-center gap-1 shrink-0" 
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        <button
          onClick={() => void handleSave()}
          className="btn-secondary h-6 px-2.5 text-[11px] font-medium tracking-wide shadow-black hover:border-zinc-500 hover:text-white"
          title="Preview & save"
        >
          <Save size={13} className="text-zinc-400" />
          Save
        </button>

        <div className="w-px h-4 bg-zinc-700 mx-2" />

        <div className="flex items-center gap-1.5 px-2 py-1 mx-1 text-[11px] font-medium text-zinc-400 rounded-md cursor-pointer transition-all hover:bg-zinc-800 hover:text-zinc-200">
          <GitBranch size={13} className="text-teal-500/80" />
          <span>{currentBranch || "workspace"}</span>
        </div>

        <button
          onClick={toggleSettings}
          className="p-1.5 rounded-md text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors cursor-pointer ml-1"
          title="Settings"
        >
          <Settings2 size={15} />
        </button>

        <button 
          className="p-1.5 rounded-md text-zinc-400 hover:text-blue-400 hover:bg-blue-900/20 transition-colors cursor-pointer" 
          title="Notifications"
        >
          <Bell size={15} />
        </button>
      </div>
    </div>
  );
}
