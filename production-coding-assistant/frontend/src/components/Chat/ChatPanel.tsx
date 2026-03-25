import { useEffect, useRef, useState } from "react";
import {
  AlertCircle, Bot, CheckCircle2, ChevronDown, ChevronUp,
  Clock, MessageSquarePlus, Paperclip, Send, Trash2, ClipboardList, MessageCircle, Cpu,
} from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { agentAPI, fileAPI, sessionsAPI } from "../../utils/api";
import { buildFileTree, formatDate, getLanguageFromFileName } from "../../utils/fileUtils";
import type { Message, SessionInfo } from "../../types";
import { motion, AnimatePresence } from "framer-motion";

type Mode = "ask" | "agent" | "plan";

/* ── helpers ─────────────────────────────────────────────────────── */
function mapMsgs(
  raw: Array<{ id: string; role: string; content: string; createdAt: string; metadata?: Record<string, unknown> }>
): Message[] {
  return raw.map((m) => {
    const plan = (m.metadata?.plan as { steps?: Message["steps"] }) ?? {};
    return { id: m.id, type: m.role === "user" ? "user" : "assistant",
      content: m.content, timestamp: new Date(m.createdAt), steps: plan.steps };
  });
}
function titleOf(s: string) {
  const t = s.trim().replace(/\s+/g, " ");
  return t.length <= 36 ? t : t.slice(0, 33) + "…";
}

/* ── Confirm dialog ──────────────────────────────────────────────── */
function ConfirmDialog({ message, onConfirm, onCancel }: {
  message: string; onConfirm(): void; onCancel(): void;
}) {
  return (
    <div className="fixed inset-0 z-[9999] bg-black/60 flex items-center justify-center backdrop-blur-sm">
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }}
        className="bg-zinc-900 border border-zinc-700 rounded-lg p-6 min-w-[320px] shadow-[0_8px_32px_rgba(0,0,0,0.8)]"
      >
        <p className="text-[13px] text-zinc-300 mb-6 leading-relaxed">{message}</p>
        <div className="flex gap-3 justify-end">
          <button onClick={onCancel} className="h-8 px-4 text-xs font-medium rounded bg-transparent border border-zinc-600 text-zinc-300 hover:bg-zinc-800 transition-colors">Cancel</button>
          <button onClick={onConfirm} className="h-8 px-4 text-xs font-bold rounded bg-red-600 border-none text-white hover:bg-red-500 shadow-md transition-colors">Delete Session</button>
        </div>
      </motion.div>
    </div>
  );
}

/* ── Plan markdown renderer ──────────────────────────────────────── */
function PlanMarkdown({ markdown }: { markdown: string }) {
  const lines = markdown.split("\n");
  return (
    <div className="text-[12px] leading-relaxed text-zinc-200">
      {lines.map((line, i) => {
        if (/^##\s+Plan:/.test(line)) {
          return <div key={i} className="font-bold text-[13px] text-teal-400 mb-2 mt-1 drop-shadow-sm">{line.replace(/^##\s+/, "")}</div>;
        }
        if (/^##/.test(line)) {
          return <div key={i} className="font-semibold text-xs text-white mt-3 mb-1">{line.replace(/^#+\s+/, "")}</div>;
        }
        if (/^\*\*(.+)\*\*$/.test(line)) {
          return <div key={i} className="font-semibold text-amber-200/90 mt-2 mb-0.5">{line.replace(/\*\*/g, "")}</div>;
        }
        if (/^\d+\.\s/.test(line)) {
          return <div key={i} className="pl-3 text-zinc-200 mb-0.5">{line}</div>;
        }
        if (/^-\s+`/.test(line)) {
          const match = line.match(/^-\s+`([^`]+)`\s*—?\s*(.*)/);
          if (match) return (
            <div key={i} className="pl-3 mb-0.5">
              <span className="font-mono text-[11px] text-sky-300 bg-sky-900/40 px-1 py-0.5 rounded shadow-sm border border-sky-800/50">{match[1]}</span>
              {match[2] && <span className="text-zinc-400"> — {match[2]}</span>}
            </div>
          );
        }
        if (/^-\s/.test(line)) {
          return <div key={i} className="pl-3 text-zinc-400 mb-0.5">{line}</div>;
        }
        if (/^---$/.test(line)) {
          return <hr key={i} className="border-none border-t border-zinc-700/50 my-2" />;
        }
        if (line.trim() === "") return <div key={i} className="h-1" />;
        const rendered = line
          .replace(/`([^`]+)`/g, `<span class="font-mono text-[11px] text-sky-300 bg-sky-900/40 px-1 py-0.5 rounded border border-sky-800/50 shadow-sm">$1</span>`)
          .replace(/\*\*([^*]+)\*\*/g, `<strong class="text-zinc-100">$1</strong>`);
        return <div key={i} className="text-zinc-400 mb-px" dangerouslySetInnerHTML={{ __html: rendered }} />;
      })}
    </div>
  );
}

/* ── Step row ────────────────────────────────────────────────────── */
function StepRow({ step, expanded, onToggle }: {
  step: NonNullable<Message["steps"]>[0]; expanded: boolean; onToggle(): void;
}) {
  const icon =
    step.status === "completed"     ? <CheckCircle2 size={13} className="text-teal-500 drop-shadow-sm" strokeWidth={2.5} />
    : step.status === "failed"      ? <AlertCircle  size={13} className="text-red-500 drop-shadow-sm" strokeWidth={2.5} />
    : step.status === "in-progress" ? <Clock size={13} className="text-amber-400" strokeWidth={2.5} />
    : <Clock size={13} className="text-zinc-600" strokeWidth={2.5} />;
  
  return (
    <div className={`flex flex-col py-1 border-b border-zinc-800/40 last:border-none ${step.status === "completed" ? "opacity-80" : ""}`}>
      <div className="flex items-center gap-2 text-[11px] font-mono whitespace-normal">
        <span className="shrink-0">{icon}</span>
        <button onClick={onToggle} className="flex-1 text-left bg-transparent border-none cursor-pointer text-zinc-300 hover:text-white transition-colors">
          {step.name}
        </button>
        <button onClick={onToggle} className="text-zinc-500 hover:text-zinc-300 transition-colors p-1 rounded hover:bg-zinc-800/50">
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>
      
      <AnimatePresence>
        {expanded && (
          <motion.div 
            initial={{ height: 0, opacity: 0 }} 
            animate={{ height: "auto", opacity: 1 }} 
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden w-full"
          >
            <div className="mt-1.5 pl-[22px] text-[11px] text-zinc-400 font-sans leading-relaxed pb-1">
              <div>{step.description}</div>
              {step.details && (
                <pre className="mt-1.5 font-mono text-[10px] bg-black/40 border border-zinc-800/60 p-1.5 rounded-md overflow-x-auto text-zinc-500 shadow-inner">
                  {step.details}
                </pre>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── Message bubble ──────────────────────────────────────────────── */
function MsgBubble({ msg }: { msg: Message }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const isUser = msg.type === "user";
  const isPlan = !isUser && msg.content.trimStart().startsWith("## Plan:");

  return (
    <motion.div 
      initial={{ opacity: 0, y: 10, scale: 0.98 }} 
      animate={{ opacity: 1, y: 0, scale: 1 }} 
      className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}
    >
      <div className={`w-6 h-6 rounded flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5 shadow-sm border ${
        isUser 
          ? "bg-gradient-to-br from-blue-500 to-indigo-600 text-white border-blue-400/30" 
          : "bg-gradient-to-br from-[#1c2c26] to-[#0f1a15] text-teal-500 border-teal-900/40"
      }`}>
        {isUser ? "U" : <Bot size={13} />}
      </div>
      
      <div className={`flex flex-col ${isUser ? "items-end" : "items-start"} max-w-[85%] ${isPlan ? "max-w-full flex-1 min-w-0" : ""}`}>
        <div className={`px-3 py-2.5 rounded-lg text-xs leading-[1.6] break-words shadow-sm ${
          isUser 
            ? "bg-[#0d3a5c]/80 text-[#b8d4f0] border border-[#1a5580]/60 rounded-tr-sm" 
            : isPlan
              ? "bg-[#0d1f1c]/40 text-zinc-200 border border-teal-900/30 w-full rounded-tl-sm shadow-inner"
              : "bg-[#18181b]/90 text-zinc-200 border border-zinc-800/80 rounded-tl-sm"
        }`}>
          {isPlan
            ? <PlanMarkdown markdown={msg.content} />
            : <div className="whitespace-pre-wrap">{msg.content}</div>
          }
          {msg.steps && msg.steps.length > 0 && (
            <div className={`mt-3 pt-2 flex flex-col gap-0.5 ${isPlan ? "border-t border-teal-900/30" : "border-t border-zinc-800/60"}`}>
              {msg.steps.map((s) => (
                <StepRow key={s.id} step={s} expanded={expanded === s.id}
                  onToggle={() => setExpanded(expanded === s.id ? null : s.id)} />
              ))}
            </div>
          )}
        </div>
        <div className="text-[10px] text-zinc-600 mt-1.5 font-medium tracking-wide px-1">
          {formatDate(msg.timestamp)}
        </div>
      </div>
    </motion.div>
  );
}

/* ── Session row ─────────────────────────────────────────────────── */
function SessionRow({ session, isActive, isSwitching, onSwitch, onDelete }: {
  session: SessionInfo; isActive: boolean; isSwitching: boolean;
  onSwitch(): void; onDelete(): void;
}) {
  return (
    <div className={`group flex items-center gap-2 h-7 px-3 relative cursor-pointer border-l-2 transition-all ${
      isActive 
        ? "bg-[#27272a]/40 border-blue-500 text-zinc-100 shadow-inner" 
        : "border-transparent text-zinc-400 hover:bg-[#18181b] hover:text-zinc-200"
    }`}>
      <button disabled={isSwitching} onClick={onSwitch}
        className="flex-1 min-w-0 text-left bg-transparent border-none cursor-pointer text-xs inherit overflow-hidden text-ellipsis whitespace-nowrap py-1 font-medium transition-colors"
      >
        {session.title}
      </button>
      <span className="text-[10px] text-zinc-600 shrink-0 mr-1.5 font-mono">
        {new Date(session.updatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
      </span>
      <button 
        onClick={(e) => { e.stopPropagation(); onDelete(); }} 
        title="Delete session"
        className="hidden group-hover:flex shrink-0 w-5 h-5 items-center justify-center p-0 bg-transparent rounded border border-transparent cursor-pointer text-zinc-500 transition-all hover:text-red-400 hover:bg-red-950/30 hover:border-red-900/40"
      >
        <Trash2 size={11} strokeWidth={2.5} />
      </button>
    </div>
  );
}

/* ── Mode config ─────────────────────────────────────────────────── */
const MODE_CONFIG: Record<Mode, { icon: React.ReactNode; placeholder: string; statusPrefix: string }> = {
  ask:   { icon: <MessageCircle size={12} strokeWidth={2.5} />, placeholder: "Ask a question about your code…", statusPrefix: "Asking AI…" },
  agent: { icon: <Cpu size={12} strokeWidth={2.5} />,           placeholder: "Ask agent to edit, create or fix files…", statusPrefix: "Agent running…" },
  plan:  { icon: <ClipboardList size={12} strokeWidth={2.5} />, placeholder: "Describe what you want to plan or research…", statusPrefix: "Planning…" },
};

/* ── Chat panel ──────────────────────────────────────────────────── */
export default function ChatPanel() {
  const {
    messages, addMessage, replaceMessages, clearMessages,
    sessionId, activeFileId, tabs, settings,
    isRightPanelOpen, setSessionId, setStatusText,
    setDiffViewer, updateTab, upsertTab, setFiles,
  } = useAppStore();

  const [input, setInput]               = useState("");
  const [loading, setLoading]           = useState(false);
  const [sessions, setSessions]         = useState<SessionInfo[]>([]);
  const [switching, setSwitching]       = useState(false);
  const [mode, setMode]                 = useState<Mode>("agent");
  const [confirmTarget, setConfirmTarget] = useState<SessionInfo | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);
  const refreshSessions = async () => setSessions(await sessionsAPI.listSessions());
  useEffect(() => { void refreshSessions(); }, [sessionId, messages.length]);

  if (!isRightPanelOpen) return null;
  const activeTab = tabs.find((t) => t.id === activeFileId);
  const modeConf  = MODE_CONFIG[mode];

  const switchSession = async (id: string) => {
    if (!id || id === sessionId) return;
    setSwitching(true);
    try {
      replaceMessages(mapMsgs(await sessionsAPI.getMessages(id)));
      setSessionId(id); setStatusText("Session switched");
    } catch (e) { setStatusText(`Switch failed: ${e instanceof Error ? e.message : e}`);
    } finally { setSwitching(false); }
  };

  const newChat = async () => {
    try {
      const s = await sessionsAPI.createSession(`Chat ${new Date().toLocaleTimeString()}`);
      setSessionId(s.id); clearMessages(); await refreshSessions();
      setStatusText("New chat started");
    } catch (e) { setStatusText(`Failed: ${e instanceof Error ? e.message : e}`); }
  };

  const executeDelete = async () => {
    if (!confirmTarget) return;
    const target = confirmTarget;
    setConfirmTarget(null);
    try {
      await sessionsAPI.deleteSession(target.id);
      const rest = sessions.filter((s) => s.id !== target.id);
      setSessions(rest);
      if (target.id === sessionId) {
        if (rest[0]) await switchSession(rest[0].id);
        else { const s = await sessionsAPI.createSession("New Chat");
          setSessionId(s.id); clearMessages(); setSessions([s]); }
      }
      setStatusText(`Deleted "${target.title}"`);
    } catch (e) { setStatusText(`Delete failed: ${e instanceof Error ? e.message : e}`); }
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
    setInput(""); setLoading(true); setStatusText(modeConf.statusPrefix);

    try {
      const res = await agentAPI.sendMessage(prompt, sid, {
        activeFilePath: activeTab?.path,
        provider: settings?.defaultProvider,
        mode,
      });
      setSessionId(res.sessionId);
      addMessage({ id: `a-${Date.now()}`, type: "assistant",
        content: res.message, timestamp: new Date(), steps: res.steps });

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
        setStatusText(mode === "plan" ? "Plan ready" : "Completed");
      }
      await refreshSessions();
    } catch (e) {
      addMessage({ id: `err-${Date.now()}`, type: "assistant",
        content: `Error: ${e instanceof Error ? e.message : e}`, timestamp: new Date() });
      setStatusText("Failed");
    } finally { setLoading(false); }
  };

  return (
    <>
      {confirmTarget && (
        <ConfirmDialog
          message={`Delete "${confirmTarget.title}"? This cannot be undone.`}
          onConfirm={() => void executeDelete()}
          onCancel={() => setConfirmTarget(null)}
        />
      )}

      <div className="w-[340px] xl:w-[380px] shrink-0 flex flex-col bg-[#0f0f11] border-l border-zinc-800/80 shadow-[-4px_0_16px_rgba(0,0,0,0.3)] z-10">
        <div className="flex items-center justify-between h-10 px-4 bg-zinc-900/60 border-b border-zinc-800/60 font-bold uppercase tracking-widest text-[11px] text-zinc-500 shrink-0 gap-2 select-none shadow-sm backdrop-blur-sm z-20 relative">
          <Bot size={15} className="text-teal-500 shrink-0 drop-shadow-[0_0_8px_rgba(20,184,166,0.3)]" strokeWidth={2.5} />
          <span className="flex-1 mt-0.5 text-zinc-300">AI Assistant</span>
          <button className="flex items-center justify-center w-6 h-6 rounded bg-transparent border-none cursor-pointer text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors" onClick={() => void newChat()} title="New chat">
            <MessageSquarePlus size={14} strokeWidth={2.5} />
          </button>
        </div>

        <div className="border-b border-zinc-800/60 max-h-[140px] overflow-y-auto shrink-0 bg-[#0f0f11] custom-scrollbar z-10 shadow-sm relative">
          {sessions.map((s) => (
            <SessionRow key={s.id} session={s} isActive={s.id === sessionId}
              isSwitching={switching} onSwitch={() => void switchSession(s.id)}
              onDelete={() => setConfirmTarget(s)} />
          ))}
          {sessions.length === 0 && (
            <div className="px-4 py-3 text-[11px] text-zinc-600 font-medium italic">
              No sessions yet
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-3.5 pb-4 pt-3 flex flex-col gap-4 min-h-0 custom-scrollbar z-0 relative">
          <AnimatePresence>
            {messages.length === 0 ? (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex-1 flex flex-col items-center justify-center text-zinc-500/70 text-sm text-center gap-3 p-6 drop-shadow-sm select-none">
                <Bot size={36} strokeWidth={1.5} className="opacity-20 mb-2" />
                <div className="font-medium tracking-wide">
                  {mode === "plan" ? "Describe a system architecture or research topic to map out." :
                   mode === "ask"  ? "Ask any question about your codebase." :
                   "Describe what features you want me to write or modify."}
                </div>
              </motion.div>
            ) : messages.map((m) => <MsgBubble key={m.id} msg={m} />)}
            {loading && (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex gap-2.5 px-1 py-1">
                <div className="w-6 h-6 rounded flex items-center justify-center shrink-0 mt-0.5 bg-gradient-to-br from-[#1c2c26] to-[#0f1a15] text-teal-500 border border-teal-900/40 shadow-sm">
                  <Bot size={13} />
                </div>
                <div className="flex items-center gap-1.5 px-3 py-2 bg-[#18181b]/90 border border-zinc-800/80 rounded-lg rounded-tl-sm shadow-sm h-8 mt-0.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-[bounce_1.4s_infinite_0s] opacity-70" />
                  <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-[bounce_1.4s_infinite_0.2s] opacity-70" />
                  <div className="w-1.5 h-1.5 rounded-full bg-zinc-500 animate-[bounce_1.4s_infinite_0.4s] opacity-70" />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <div ref={endRef} className="h-0 shrink-0" />
        </div>

        <div className="shrink-0 border-t border-zinc-800/80 bg-[#121214] z-20 shadow-[0_-4px_16px_rgba(0,0,0,0.3)] backdrop-blur-md pb-2">
          {/* Mode selector */}
          <div className="flex items-center gap-1.5 px-3.5 pt-3 pb-1">
            {(["ask", "agent", "plan"] as const).map((m) => (
              <button key={m} className={`h-[24px] px-2.5 text-[11px] font-bold rounded shadow-sm border cursor-pointer transition-all flex items-center gap-1.5 ${
                mode === m 
                  ? "text-zinc-100 bg-zinc-700/60 border-zinc-600 drop-shadow-md" 
                  : "text-zinc-400 bg-transparent border-transparent hover:text-white hover:bg-zinc-800"
              }`}
                onClick={() => setMode(m)}>
                {MODE_CONFIG[m].icon}
                {m.charAt(0).toUpperCase() + m.slice(1)}
              </button>
            ))}
            <div className="ml-auto flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-zinc-400 bg-zinc-900/80 border border-zinc-800 rounded px-2.5 py-1 cursor-pointer hover:border-blue-500/60 hover:text-zinc-200 transition-colors shadow-inner">
              <Bot size={11} className="text-teal-500 drop-shadow-sm" />
              {settings?.defaultProvider || "groq"}
              <ChevronDown size={11} strokeWidth={2.5} />
            </div>
          </div>

          <div className="px-3.5 py-1.5">
            <textarea rows={3} value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }}
              placeholder={modeConf.placeholder}
              className="w-full min-h-[60px] max-h-[160px] resize-none bg-[#09090b] shadow-inner border border-zinc-700/80 rounded-md px-3 py-2 text-[13px] font-sans text-white leading-relaxed transition-colors placeholder:text-zinc-600 focus:outline-none focus:border-blue-500/70 focus:bg-[#121214]"
            />
          </div>

          <div className="flex items-center px-3.5 pb-1 gap-2">
            <button className="w-7 h-7 flex items-center justify-center rounded bg-transparent border-none cursor-pointer text-zinc-400 hover:bg-zinc-800 hover:text-white transition-colors" title="Attach file"><Paperclip size={14} strokeWidth={2} /></button>
            <button className="ml-auto flex items-center gap-2 h-7 px-3.5 text-[11px] font-bold uppercase tracking-widest rounded bg-blue-600 text-white border-none shadow drop-shadow-sm cursor-pointer transition-transform active:scale-95 hover:bg-blue-500 disabled:bg-zinc-800 disabled:text-zinc-600 disabled:cursor-not-allowed disabled:shadow-none disabled:active:scale-100" onClick={() => void send()}
              disabled={!input.trim() || loading || switching}>
              <Send size={12} strokeWidth={2.5} className={(loading || switching) ? "opacity-50" : ""} />
              {mode === "plan" ? "Plan" : mode === "ask" ? "Ask" : "Send"}
            </button>
          </div>

          <div className="px-4 text-[10px] text-zinc-500/70 flex gap-1.5 items-center font-medium">
            <kbd className="bg-zinc-800/50 border border-zinc-700/50 rounded-sm px-1 font-sans shadow-inner text-zinc-400">Enter</kbd> to send &nbsp;·&nbsp; 
            <kbd className="bg-zinc-800/50 border border-zinc-700/50 rounded-sm px-1 font-sans shadow-inner text-zinc-400">Shift + Enter</kbd> for newline
          </div>
        </div>
      </div>
    </>
  );
}
