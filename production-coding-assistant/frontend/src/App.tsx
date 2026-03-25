import { useEffect } from "react";
import ActivityBar from "./components/ActivityBar/ActivityBar";
import TopBar from "./components/TopBar/TopBar";
import Sidebar from "./components/Sidebar/Sidebar";
import EditorPanel from "./components/Editor/EditorPanel";
import ChatPanel from "./components/Chat/ChatPanel";
import TerminalPanel from "./components/Terminal/TerminalPanel";
import DiffViewer from "./components/DiffViewer/DiffViewer";
import SettingsDrawer from "./components/Settings/SettingsDrawer";
import { useAppStore } from "./store/useAppStore";
import { buildFileTree } from "./utils/fileUtils";
import { fileAPI, healthCheck, sessionsAPI, settingsAPI } from "./utils/api";
import { GitBranch, Wifi, WifiOff, CheckCircle2 } from "lucide-react";
import type { Message } from "./types";

function mapStoredMessages(
  messages: Array<{ id: string; role: string; content: string; createdAt: string; metadata?: Record<string, unknown> }>
): Message[] {
  return messages.map((m) => {
    const plan = (m.metadata?.plan as { steps?: Message["steps"] }) ?? {};
    return { id: m.id, type: m.role === "user" ? "user" : "assistant", content: m.content, timestamp: new Date(m.createdAt), steps: plan.steps };
  });
}

export default function App() {
  const setFiles       = useAppStore((s) => s.setFiles);
  const setSessionId   = useAppStore((s) => s.setSessionId);
  const replaceMessages = useAppStore((s) => s.replaceMessages);
  const setSettings    = useAppStore((s) => s.setSettings);
  const setStatusText  = useAppStore((s) => s.setStatusText);
  const setCurrentBranch = useAppStore((s) => s.setCurrentBranch);
  const statusText     = useAppStore((s) => s.statusText);
  const currentBranch  = useAppStore((s) => s.currentBranch);
  const settings       = useAppStore((s) => s.settings);
  const activeFileId   = useAppStore((s) => s.activeFileId);
  const tabs           = useAppStore((s) => s.tabs);
  const activeTab      = tabs.find((t) => t.id === activeFileId);

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const healthy = await healthCheck();
        if (!healthy) { setStatusText("Backend unavailable"); return; }

        const [files, settings, sessions] = await Promise.all([
          fileAPI.listFiles(),
          settingsAPI.get(),
          sessionsAPI.listSessions(),
        ]);

        setFiles(buildFileTree(files));
        setSettings(settings);
        setCurrentBranch("workspace");

        const session = sessions[0] ?? (await sessionsAPI.createSession("Production Assistant"));
        setSessionId(session.id);

        const msgs = await sessionsAPI.getMessages(session.id);
        replaceMessages(mapStoredMessages(msgs));
        setStatusText(`Ready · ${settings.defaultProvider} · ${files.filter((f) => f.type === "file").length} files`);
      } catch (err) {
        setStatusText(`Startup failed: ${err instanceof Error ? err.message : "Unknown"}`);
      }
    };
    void bootstrap();
  }, [replaceMessages, setCurrentBranch, setFiles, setSessionId, setSettings, setStatusText]);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-zinc-950 text-zinc-100 font-sans selection:bg-blue-500/30">
      {/* Title / menu bar */}
      <TopBar />

      {/* Main body */}
      <div className="flex flex-1 overflow-hidden relative">
        <ActivityBar />
        <Sidebar />

        <div className="flex flex-1 flex-col min-w-0 overflow-hidden bg-[#09090b] shadow-inner relative z-0">
          <EditorPanel />
          <TerminalPanel />
        </div>

        <ChatPanel />
      </div>

      {/* Status bar */}
      <div className="flex items-center h-6 shrink-0 bg-zinc-900 border-t border-zinc-800 px-3 text-[11px] text-zinc-400 gap-3 font-medium shadow-[0_-1px_3px_rgba(0,0,0,0.2)]">
        <div className="flex items-center gap-1.5 hover:text-zinc-200 cursor-pointer transition-colors px-1 h-full">
          <GitBranch size={11} className="text-teal-500" />
          <span>{currentBranch || "workspace"}</span>
        </div>

        {activeTab && (
          <>
            <div className="flex items-center hover:text-zinc-200 cursor-pointer transition-colors px-1 h-full">
              <span>{activeTab.language || "plaintext"}</span>
            </div>
            <div className="flex items-center gap-1.5 hover:text-zinc-200 cursor-pointer transition-colors px-1 h-full">
              {activeTab.isDirty ? <span className="w-2 h-2 rounded-full bg-zinc-300" /> : <CheckCircle2 size={10} className="text-teal-500" />}
              <span>{activeTab.name}</span>
            </div>
          </>
        )}

        <div className="flex-1" />

        <div className="flex items-center text-[10px] text-zinc-500 max-w-[40vw] truncate">
          {statusText}
        </div>

        <div className="flex items-center gap-1.5 hover:text-zinc-200 cursor-pointer transition-colors px-1 h-full">
          {settings
            ? <><Wifi size={10} className="text-blue-400" /><span>{settings.defaultProvider}</span></>
            : <><WifiOff size={10} className="text-zinc-600" /><span>connecting…</span></>
          }
        </div>
      </div>

      {/* Overlays */}
      <DiffViewer />
      <SettingsDrawer />
    </div>
  );
}
