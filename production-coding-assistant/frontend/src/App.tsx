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
    <div className="ide-layout">
      {/* Title / menu bar */}
      <TopBar />

      {/* Main body */}
      <div className="ide-body">
        <ActivityBar />
        <Sidebar />

        <div className="ide-main">
          <EditorPanel />
          <TerminalPanel />
        </div>

        <ChatPanel />
      </div>

      {/* Status bar */}
      <div className="statusbar">
        <div className="statusbar-item" title="Branch">
          <GitBranch size={12} />
          <span>{currentBranch || "workspace"}</span>
        </div>

        {activeTab && (
          <>
            <div className="statusbar-item">
              <span>{activeTab.language || "plaintext"}</span>
            </div>
            <div className="statusbar-item">
              <span>{activeTab.isDirty ? "●" : <CheckCircle2 size={10} />}</span>
              <span>{activeTab.name}</span>
            </div>
          </>
        )}

        <div className="statusbar-sep" />

        <div className="statusbar-item" style={{ fontSize: 11, opacity: 0.8 }}>
          {statusText}
        </div>

        <div className="statusbar-item">
          {settings
            ? <><Wifi size={11} /><span>{settings.defaultProvider}</span></>
            : <><WifiOff size={11} /><span>connecting…</span></>
          }
        </div>
      </div>

      {/* Overlays */}
      <DiffViewer />
      <SettingsDrawer />
    </div>
  );
}
