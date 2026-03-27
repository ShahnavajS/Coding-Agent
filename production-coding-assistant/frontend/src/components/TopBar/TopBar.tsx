import type { CSSProperties } from "react";
import { Bell, GitBranch, Save, Settings2 } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { fileAPI } from "../../utils/api";

export default function TopBar() {
  const {
    toggleSettings,
    tabs,
    activeFileId,
    setStatusText,
    statusText,
    currentBranch,
    settings,
  } = useAppStore();

  const activeTab = tabs.find((tab) => tab.id === activeFileId);

  const handleSave = async () => {
    if (!activeTab) {
      setStatusText("No file selected");
      return;
    }

    try {
      await fileAPI.writeFile(activeTab.path, activeTab.content);
      useAppStore.getState().updateTab(activeTab.id, { isDirty: false });
      setStatusText(`Saved ${activeTab.path}`);
    } catch (error) {
      setStatusText(
        `Save failed: ${error instanceof Error ? error.message : "Unknown"}`
      );
    }
  };

  return (
    <div
      className="flex h-10 shrink-0 items-center gap-4 border-b border-zinc-800/80 bg-dark-surface/90 px-4 backdrop-blur-md"
      style={{ WebkitAppRegion: "drag" } as CSSProperties}
    >
      <div
        className="flex shrink-0 items-center gap-3"
        style={{ WebkitAppRegion: "no-drag" } as CSSProperties}
      >
        <span className="font-mono text-[13px] font-semibold tracking-wide text-zinc-200">
          Production AI Assistant
        </span>
        <span className="rounded-full border border-zinc-700 bg-zinc-800/60 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-teal-400">
          {settings?.defaultProvider || "groq"}
        </span>
      </div>

      <div
        className="flex-1 truncate px-6 text-center text-xs font-medium uppercase tracking-widest text-zinc-500"
        style={{ WebkitAppRegion: "drag" } as CSSProperties}
      >
        {statusText}
      </div>

      <div
        className="flex shrink-0 items-center gap-1"
        style={{ WebkitAppRegion: "no-drag" } as CSSProperties}
      >
        <button
          onClick={() => void handleSave()}
          className="btn-secondary h-6 px-2.5 text-[11px] font-medium tracking-wide shadow-black hover:border-zinc-500 hover:text-white"
          title="Save file"
        >
          <Save size={13} className="text-zinc-400" />
          Save
        </button>

        <div className="mx-2 h-4 w-px bg-zinc-700" />

        <div className="mx-1 flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-medium text-zinc-400 transition-all hover:bg-zinc-800 hover:text-zinc-200">
          <GitBranch size={13} className="text-teal-500/80" />
          <span>{currentBranch || "workspace"}</span>
        </div>

        <button
          onClick={toggleSettings}
          className="ml-1 rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
          title="Settings"
        >
          <Settings2 size={15} />
        </button>

        <button
          className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-blue-900/20 hover:text-blue-400"
          title="Notifications"
        >
          <Bell size={15} />
        </button>
      </div>
    </div>
  );
}
