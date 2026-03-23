import { useEffect, useRef, useState } from "react";
import {
  AlertCircle, Bot, CheckCircle2, ChevronDown, ChevronUp,
  Clock, MessageSquarePlus, Paperclip, Send, Trash2, X,
} from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { agentAPI, fileAPI, sessionsAPI } from "../../utils/api";
import { buildFileTree, formatDate, getLanguageFromFileName } from "../../utils/fileUtils";
import type { Message, SessionInfo } from "../../types";

/* ── helpers ─────────────────────────────────────────────────────── */
function mapMsgs(
  raw: Array<{ id: string; role: string; content: string; createdAt: string; metadata?: Record<string, unknown> }>
): Message[] {
  return raw.map((m) => {
    const plan = (m.metadata?.plan as { steps?: Message["steps"] }) ?? {};
    return {
      id: m.id,
      type: m.role === "user" ? "user" : "assistant",
      content: m.content,
      timestamp: new Date(m.createdAt),
      steps: plan.steps,
    };
  });
}

function titleOf(s: string) {
  const t = s.trim().replace(/\s+/g, " ");
  return t.length <= 36 ? t : t.slice(0, 33) + "…";
}

/* ── Confirm dialog (replaces window.confirm — works in Electron) ── */
function ConfirmDialog({
  message,
  onConfirm,
  onCancel,
}: {
  message: string;
  onConfirm(): void;
  onCancel(): void;
}) {
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.5)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        background: "#252526", border: "1px solid #3d3d3d",
        borderRadius: 6, padding: "20px 24px", minWidth: 280,
        boxShadow: "0 8px 32px rgba(0,0,0,0.6)",
      }}>
        <div style={{ fontSize: 13, color: "#cccccc", marginBottom: 16, lineHeight: 1.5 }}>
          {message}
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button
            onClick={onCancel}
            style={{
              height: 26, padding: "0 12px", fontSize: 12,
              background: "transparent", border: "1px solid #3d3d3d",
              borderRadius: 3, color: "#cccccc", cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            style={{
              height: 26, padding: "0 12px", fontSize: 12,
              background: "#5a1d1d", border: "1px solid #6e2020",
              borderRadius: 3, color: "#f97583", cursor: "pointer",
            }}
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Step row ────────────────────────────────────────────────────── */
function StepRow({
  step, expanded, onToggle,
}: {
  step: NonNullable<Message["steps"]>[0];
  expanded: boolean;
  onToggle(): void;
}) {
  const icon =
    step.status === "completed"    ? <CheckCircle2 size={12} style={{ color: "var(--accent-teal)" }} />
    : step.status === "failed"     ? <AlertCircle  size={12} style={{ color: "var(--accent-red)" }} />
    : step.status === "in-progress"? <Clock size={12} style={{ color: "#dcdcaa" }} />
    : <Clock size={12} style={{ color: "var(--text-inactive)" }} />;

  return (
    <div className={`step-row${step.status === "completed" ? " done" : step.status === "failed" ? " error" : ""}`}>
      {icon}
      <button
        onClick={onToggle}
        style={{ flex: 1, textAlign: "left", background: "none", border: "none",
          cursor: "pointer", color: "inherit", fontSize: "inherit", fontFamily: "inherit" }}
      >
        {step.name}
      </button>
      {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
      {expanded && (
        <div style={{ width: "100%", marginTop: 4, paddingLeft: 18, fontSize: 11,
          color: "var(--text-secondary)", lineHeight: 1.6 }}>
          <div>{step.description}</div>
          {step.details && (
            <pre style={{ marginTop: 4, fontFamily: "var(--font-mono)", fontSize: 10,
              background: "var(--bg)", padding: "4px 6px", borderRadius: 3, overflowX: "auto" }}>
              {step.details}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Message bubble ──────────────────────────────────────────────── */
function MsgBubble({ msg }: { msg: Message }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const isUser = msg.type === "user";

  return (
    <div className={`msg-row${isUser ? " user" : ""}`}>
      <div className={`msg-avatar ${isUser ? "user-av" : "ai-av"}`}>
        {isUser ? "U" : <Bot size={12} />}
      </div>
      <div>
        <div className={`msg-bubble ${isUser ? "user" : "ai"}`}>
          <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{msg.content}</div>
          {msg.steps && msg.steps.length > 0 && (
            <div className="msg-steps">
              {msg.steps.map((s) => (
                <StepRow
                  key={s.id} step={s}
                  expanded={expanded === s.id}
                  onToggle={() => setExpanded(expanded === s.id ? null : s.id)}
                />
              ))}
            </div>
          )}
        </div>
        <div className="msg-time">{formatDate(msg.timestamp)}</div>
      </div>
    </div>
  );
}

/* ── Session row ─────────────────────────────────────────────────── */
function SessionRow({
  session,
  isActive,
  isSwitching,
  onSwitch,
  onDelete,
}: {
  session: SessionInfo;
  isActive: boolean;
  isSwitching: boolean;
  onSwitch(): void;
  onDelete(): void;
}) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      className={`chat-session-item${isActive ? " active" : ""}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        disabled={isSwitching}
        onClick={onSwitch}
        style={{
          flex: 1, textAlign: "left", background: "none", border: "none",
          cursor: "pointer", fontSize: 12, color: "inherit",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          minWidth: 0,
        }}
      >
        {session.title}
      </button>

      {/* Always render time OR delete button — delete only when hovered */}
      {hovered ? (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          title="Delete session"
          style={{
            flexShrink: 0, width: 18, height: 18,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "transparent", border: "none", cursor: "pointer",
            color: "#f44747", borderRadius: 3, padding: 0,
          }}
        >
          <Trash2 size={12} />
        </button>
      ) : (
        <span style={{ fontSize: 10, color: "var(--text-inactive)", flexShrink: 0 }}>
          {new Date(session.updatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>
      )}
    </div>
  );
}

/* ── Chat panel ──────────────────────────────────────────────────── */
export default function ChatPanel() {
  const {
    messages, addMessage, replaceMessages, clearMessages,
    sessionId, activeFileId, tabs, settings,
    isRightPanelOpen, setSessionId, setStatusText,
    setDiffViewer, updateTab, upsertTab, setFiles,
  } = useAppStore();

  const [input, setInput]         = useState("");
  const [loading, setLoading]     = useState(false);
  const [sessions, setSessions]   = useState<SessionInfo[]>([]);
  const [switching, setSwitching] = useState(false);
  const [mode, setMode]           = useState<"ask" | "agent" | "plan">("agent");
  const [confirmTarget, setConfirmTarget] = useState<SessionInfo | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const refreshSessions = async () => setSessions(await sessionsAPI.listSessions());
  useEffect(() => { void refreshSessions(); }, [sessionId, messages.length]);

  if (!isRightPanelOpen) return null;

  const activeTab = tabs.find((t) => t.id === activeFileId);

  const switchSession = async (id: string) => {
    if (!id || id === sessionId) return;
    setSwitching(true);
    try {
      replaceMessages(mapMsgs(await sessionsAPI.getMessages(id)));
      setSessionId(id);
      setStatusText("Session switched");
    } catch (e) {
      setStatusText(`Switch failed: ${e instanceof Error ? e.message : e}`);
    } finally { setSwitching(false); }
  };

  const newChat = async () => {
    try {
      const s = await sessionsAPI.createSession(`Chat ${new Date().toLocaleTimeString()}`);
      setSessionId(s.id); clearMessages(); await refreshSessions();
      setStatusText("New chat started");
    } catch (e) {
      setStatusText(`Failed: ${e instanceof Error ? e.message : e}`);
    }
  };

  /* Delete uses our custom dialog — NOT window.confirm (broken in Electron) */
  const confirmDelete = (target: SessionInfo) => setConfirmTarget(target);

  const executeDelete = async () => {
    if (!confirmTarget) return;
    const target = confirmTarget;
    setConfirmTarget(null);
    try {
      await sessionsAPI.deleteSession(target.id);
      const rest = sessions.filter((s) => s.id !== target.id);
      setSessions(rest);
      if (target.id === sessionId) {
        if (rest[0]) {
          await switchSession(rest[0].id);
        } else {
          const s = await sessionsAPI.createSession("New Chat");
          setSessionId(s.id); clearMessages(); setSessions([s]);
        }
      }
      setStatusText(`Deleted "${target.title}"`);
    } catch (e) {
      setStatusText(`Delete failed: ${e instanceof Error ? e.message : e}`);
    }
  };

  const send = async () => {
    if (!input.trim()) return;
    const prompt = input;
    let sid = sessionId;
    if (!sid) {
      const s = await sessionsAPI.createSession(titleOf(prompt));
      sid = s.id; setSessionId(sid); clearMessages(); await refreshSessions();
    }
    addMessage({ id: `u-${Date.now()}`, type: "user", content: prompt, timestamp: new Date() });
    setInput(""); setLoading(true); setStatusText("Agent running…");

    try {
      const res = await agentAPI.sendMessage(prompt, sid, {
        activeFilePath: activeTab?.path,
        provider: settings?.defaultProvider,
      });
      setSessionId(res.sessionId);
      addMessage({
        id: `a-${Date.now()}`, type: "assistant",
        content: res.message, timestamp: new Date(), steps: res.steps,
      });

      if (res.diffPreview) {
        const p = res.diffPreview;
        setDiffViewer({
          isOpen: true, diffId: p.id, fileName: p.path,
          originalContent: p.originalContent, modifiedContent: p.modifiedContent,
          validation: p.validation,
          onAccept: async () => {
            const result = await fileAPI.applyDiff(p.id);
            const files = await fileAPI.listFiles(); setFiles(buildFileTree(files));
            const name = p.path.split("/").pop() ?? p.path;
            const tid = tabs.find((t) => t.path === p.path)?.id ?? p.path;
            upsertTab({ id: tid, name, path: p.path, content: p.modifiedContent,
              language: getLanguageFromFileName(name), isDirty: false });
            updateTab(tid, { isDirty: false });
            setStatusText(`Applied · checkpoint ${result.checkpoint.id.slice(0, 8)}`);
          },
          onReject: () => setStatusText(`Rejected diff for ${p.path}`),
        });
        setStatusText(`Diff ready · ${p.path}`);
      } else {
        setStatusText("Agent completed");
      }
      await refreshSessions();
    } catch (e) {
      addMessage({
        id: `err-${Date.now()}`, type: "assistant",
        content: `Error: ${e instanceof Error ? e.message : e}`,
        timestamp: new Date(),
      });
      setStatusText("Agent failed");
    } finally { setLoading(false); }
  };

  return (
    <>
      {/* Custom confirm dialog — replaces window.confirm which fails in Electron */}
      {confirmTarget && (
        <ConfirmDialog
          message={`Delete "${confirmTarget.title}"?`}
          onConfirm={() => void executeDelete()}
          onCancel={() => setConfirmTarget(null)}
        />
      )}

      <div className="chat-panel">
        {/* Header */}
        <div className="chat-header">
          <Bot size={13} style={{ color: "var(--accent-teal)", flexShrink: 0 }} />
          <span style={{ flex: 1 }}>AI Assistant</span>
          <button className="chat-header-new-btn" onClick={() => void newChat()} title="New chat">
            <MessageSquarePlus size={13} />
          </button>
        </div>

        {/* Sessions list */}
        <div className="chat-sessions">
          {sessions.map((s) => (
            <SessionRow
              key={s.id}
              session={s}
              isActive={s.id === sessionId}
              isSwitching={switching}
              onSwitch={() => void switchSession(s.id)}
              onDelete={() => confirmDelete(s)}
            />
          ))}
          {sessions.length === 0 && (
            <div style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-inactive)" }}>
              No sessions yet
            </div>
          )}
        </div>

        {/* Messages */}
        <div className="chat-messages">
          {messages.length === 0 ? (
            <div className="chat-empty">
              <Bot size={28} style={{ opacity: 0.2 }} />
              <div>Ask the agent to inspect,<br />explain, or modify code</div>
            </div>
          ) : (
            messages.map((m) => <MsgBubble key={m.id} msg={m} />)
          )}
          {loading && (
            <div className="msg-row" style={{ padding: "0 4px" }}>
              <div className="msg-avatar ai-av"><Bot size={12} /></div>
              <div style={{ display: "flex", gap: 4, alignItems: "center", padding: "8px 0" }}>
                <div className="typing-dot" />
                <div className="typing-dot" />
                <div className="typing-dot" />
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* Input area */}
        <div className="chat-input-area">
          <div className="chat-mode-bar">
            {(["ask", "agent", "plan"] as const).map((m) => (
              <button
                key={m}
                className={`chat-mode-btn${mode === m ? " active" : ""}`}
                onClick={() => setMode(m)}
              >
                {m.charAt(0).toUpperCase() + m.slice(1)}
              </button>
            ))}
            <div className="chat-model-pill">
              <Bot size={10} style={{ color: "var(--accent-teal)" }} />
              {settings?.defaultProvider || "groq"}
              <ChevronDown size={10} />
            </div>
          </div>

          <div className="chat-textarea-wrap">
            <textarea
              rows={3}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
              }}
              placeholder="Ask anything… Shift+Enter for newline"
            />
          </div>

          <div className="chat-toolbar">
            <button className="chat-toolbar-btn" title="Attach file">
              <Paperclip size={13} />
            </button>
            <button
              className="chat-send-btn"
              onClick={() => void send()}
              disabled={!input.trim() || loading || switching}
            >
              <Send size={12} />
              Send
            </button>
          </div>

          <div className="chat-hint">
            <kbd>Enter</kbd> send &nbsp;·&nbsp; <kbd>Shift</kbd><kbd>Enter</kbd> newline
          </div>
        </div>
      </div>
    </>
  );
}
