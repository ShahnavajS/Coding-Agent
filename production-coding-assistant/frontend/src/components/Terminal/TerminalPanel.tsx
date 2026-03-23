import { useEffect, useRef, useState } from "react";
import { Play, ShieldAlert, Trash2, Maximize2 } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { terminalAPI } from "../../utils/api";

type PanelTab = "terminal" | "logs" | "errors";

function lineClass(line: string): string {
  if (line.startsWith("$")) return "terminal-output-line cmd";
  if (line.startsWith("[stderr]") || line.startsWith("[error]")) return "terminal-output-line err";
  if (line.startsWith("[approval]")) return "terminal-output-line warn";
  if (line.startsWith("[exit")) return "terminal-output-line dim";
  return "terminal-output-line";
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
    <div className="terminal-panel">
      {/* Panel tabs bar */}
      <div className="panel-tabs">
        {(["terminal", "logs", "errors"] as PanelTab[]).map((t) => (
          <button
            key={t}
            className={`panel-tab${activeTab === t ? " active" : ""}`}
            onClick={() => setActiveTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
        <div className="panel-tab-spacer" />
        <button className="panel-action-btn" title="Clear" onClick={clearTerminal}>
          <Trash2 size={13} />
        </button>
        <button className="panel-action-btn" title="Maximise">
          <Maximize2 size={13} />
        </button>
      </div>

      {/* Output */}
      <div className="terminal-output">
        {terminal.output.length === 0 ? (
          <span className="terminal-output-line dim">
            {activeTab === "terminal" && "Guarded shell access is ready. Risky commands require approval."}
            {activeTab === "logs"     && "No logs yet."}
            {activeTab === "errors"   && "No errors."}
          </span>
        ) : (
          terminal.output.map((line, i) => (
            <div key={i} className={lineClass(line)}>{line}</div>
          ))
        )}
        <div ref={outputEndRef} />
      </div>

      {/* Input row */}
      <div className="terminal-input-row">
        <span className="terminal-prompt">›</span>
        <input
          className="terminal-input"
          type="text"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void runCommand(); }}
          placeholder="Enter command…"
          disabled={terminal.isRunning}
        />
        {terminal.approvalRequired && (
          <button className="btn-danger" style={{ height: 22, padding: "0 8px", fontSize: 11, gap: 4 }} onClick={() => void runCommand(true)}>
            <ShieldAlert size={12} />
            Approve
          </button>
        )}
        <button
          className="btn-primary"
          style={{ height: 22, width: 28, padding: 0, justifyContent: "center" }}
          onClick={() => void runCommand()}
          disabled={terminal.isRunning || !command.trim()}
          title="Run"
        >
          <Play size={12} />
        </button>
      </div>
    </div>
  );
}
