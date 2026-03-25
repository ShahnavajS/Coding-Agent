import { useEffect, useRef, useState } from "react";
import { Play, ShieldAlert, Trash2, Maximize2 } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { terminalAPI } from "../../utils/api";

type PanelTab = "terminal" | "logs" | "errors";

function lineClass(line: string): string {
  if (line.startsWith("$")) return "text-teal-400 font-medium drop-shadow-sm";
  if (line.startsWith("[stderr]") || line.startsWith("[error]")) return "text-red-400";
  if (line.startsWith("[approval]")) return "text-amber-400 font-medium";
  if (line.startsWith("[exit")) return "text-zinc-500 italic";
  return "text-zinc-300";
}

export default function TerminalPanel() {
  const {
    terminal, addTerminalOutput, clearTerminal,
    setTerminalApprovalRequired, setTerminalRunning,
    isBottomPanelOpen, setStatusText,
  } = useAppStore();

  const [command, setCommand] = useState("");
  const [activeTab, setActiveTab] = useState<PanelTab>("terminal");
  const outputEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    outputEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [terminal.output]);

  if (!isBottomPanelOpen) return null;

  const runCommand = async (approved = false) => {
    const cmd = command.trim();
    if (!cmd && !approved) return;
    if (!approved) addTerminalOutput(`$ ${cmd}`);
    setTerminalRunning(true);
    setTerminalApprovalRequired(false);
    try {
      const result = await terminalAPI.executeCommand(cmd, approved);
      if (result.requiresApproval) {
        addTerminalOutput(`[approval] ${result.stderr}`);
        setTerminalApprovalRequired(true);
        setStatusText("Command requires approval");
        return;
      }
      if (result.stdout) addTerminalOutput(result.stdout.trimEnd());
      if (result.stderr) addTerminalOutput(`[stderr] ${result.stderr.trimEnd()}`);
      addTerminalOutput(`[exit ${result.exitCode ?? "?"}]`);
      setStatusText("Done");
      setCommand("");
    } catch (e) {
      addTerminalOutput(`[error] ${e instanceof Error ? e.message : "Unknown error"}`);
      setStatusText("Command failed");
    } finally {
      setTerminalRunning(false);
    }
  };

  return (
    <div className="flex flex-col h-[260px] shrink-0 bg-[#0f0f11] border-t border-[#27272a] shadow-[0_-4px_12px_rgba(0,0,0,0.4)] z-10 relative">
      {/* Panel tabs bar */}
      <div className="flex items-center h-8 bg-[#18181b] border-b border-[#27272a] px-2 shrink-0 select-none">
        {(["terminal", "logs", "errors"] as PanelTab[]).map((t) => (
          <button
            key={t}
            className={`h-8 px-4 text-xs font-medium border-b-2 transition-colors cursor-pointer ${
              activeTab === t 
                ? "text-zinc-100 border-blue-500 bg-[#0f0f11]" 
                : "text-zinc-400 border-transparent hover:text-zinc-200 bg-transparent"
            }`}
            onClick={() => setActiveTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
        <div className="flex-1" />
        <div className="flex items-center gap-1.5 px-2">
          <button 
            className="w-6 h-6 flex items-center justify-center rounded text-zinc-400 bg-transparent hover:bg-zinc-800 hover:text-red-400 transition-colors cursor-pointer" 
            title="Clear" 
            onClick={clearTerminal}
          >
            <Trash2 size={13} strokeWidth={2} />
          </button>
          <button 
            className="w-6 h-6 flex items-center justify-center rounded text-zinc-400 bg-transparent hover:bg-zinc-800 hover:text-zinc-100 transition-colors cursor-pointer" 
            title="Maximise"
          >
            <Maximize2 size={13} strokeWidth={2} />
          </button>
        </div>
      </div>

      {/* Output */}
      <div className="flex-1 overflow-y-auto px-4 py-2 font-mono text-[11px] leading-relaxed bg-[#0b0b0c] custom-scrollbar shadow-inner select-text">
        {terminal.output.length === 0 ? (
          <div className="text-zinc-600 italic">
            {activeTab === "terminal" && "Agent shell. Background commands execute safely with required supervision."}
            {activeTab === "logs"     && "No logs stream active."}
            {activeTab === "errors"   && "No system errors."}
          </div>
        ) : (
          terminal.output.map((line, i) => (
            <div key={i} className={`whitespace-pre-wrap break-all ${lineClass(line)}`}>
              {line}
            </div>
          ))
        )}
        <div ref={outputEndRef} />
      </div>

      {/* Input row */}
      <div className="flex items-center h-8 border-t border-[#27272a] px-3 gap-2 shrink-0 bg-[#121214]">
        <span className="text-teal-400 font-mono text-sm shrink-0 font-bold ml-1">›</span>
        <input
          className="flex-1 h-full bg-transparent border-none outline-none font-mono text-xs text-zinc-200 placeholder-zinc-600 disabled:opacity-50"
          type="text"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void runCommand(); }}
          placeholder="Issue root shell command..."
          disabled={terminal.isRunning}
        />
        {terminal.approvalRequired && (
          <button 
            className="flex items-center gap-1.5 h-6 px-2.5 text-[10px] uppercase font-bold tracking-wide rounded border border-red-900/50 bg-red-950/40 text-red-400 hover:bg-red-900/60 transition-colors cursor-pointer" 
            onClick={() => void runCommand(true)}
          >
            <ShieldAlert size={12} strokeWidth={2.5} />
            Approve
          </button>
        )}
        <button
          className="flex items-center justify-center w-7 h-6 rounded bg-blue-600 text-white disabled:bg-zinc-800 disabled:text-zinc-600 hover:animate-pulse transition-colors cursor-pointer disabled:cursor-not-allowed"
          onClick={() => void runCommand()}
          disabled={terminal.isRunning || !command.trim()}
          title="Run"
        >
          <Play size={12} className={terminal.isRunning ? "" : "ml-0.5"} />
        </button>
      </div>
    </div>
  );
}
