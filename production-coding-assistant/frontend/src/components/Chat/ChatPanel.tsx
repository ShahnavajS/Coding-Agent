import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  Clock,
  Cpu,
  MessageCircle,
  MessageSquarePlus,
  Paperclip,
  Send,
  Trash2,
} from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useAppStore } from "../../store/useAppStore";
import { agentAPI, fileAPI, sessionsAPI } from "../../utils/api";
import {
  buildFileTree,
  formatDate,
  getLanguageFromFileName,
} from "../../utils/fileUtils";
import type { Message, SessionInfo } from "../../types";

type Mode = "ask" | "agent" | "plan";

function mapMsgs(
  raw: Array<{
    id: string;
    role: string;
    content: string;
    createdAt: string;
    metadata?: Record<string, unknown>;
  }>
): Message[] {
  return raw.map((message) => {
    const plan = (message.metadata?.plan as { steps?: Message["steps"] }) ?? {};
    return {
      id: message.id,
      type: message.role === "user" ? "user" : "assistant",
      content: message.content,
      timestamp: new Date(message.createdAt),
      steps: plan.steps,
    };
  });
}

function titleOf(text: string) {
  const cleaned = text.trim().replace(/\s+/g, " ");
  return cleaned.length <= 36 ? cleaned : `${cleaned.slice(0, 33)}...`;
}

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
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className="min-w-[320px] rounded-lg border border-zinc-700 bg-zinc-900 p-6 shadow-[0_8px_32px_rgba(0,0,0,0.8)]"
      >
        <p className="mb-6 text-[13px] leading-relaxed text-zinc-300">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="h-8 rounded border border-zinc-600 bg-transparent px-4 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-800"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="h-8 rounded bg-red-600 px-4 text-xs font-bold text-white transition-colors hover:bg-red-500"
          >
            Delete Session
          </button>
        </div>
      </motion.div>
    </div>
  );
}

function StepRow({
  step,
  expanded,
  onToggle,
}: {
  step: NonNullable<Message["steps"]>[0];
  expanded: boolean;
  onToggle(): void;
}) {
  const icon =
    step.status === "completed" ? (
      <CheckCircle2 size={13} className="text-teal-500" strokeWidth={2.5} />
    ) : step.status === "failed" ? (
      <AlertCircle size={13} className="text-red-500" strokeWidth={2.5} />
    ) : step.status === "in-progress" ? (
      <Clock size={13} className="text-amber-400" strokeWidth={2.5} />
    ) : (
      <Clock size={13} className="text-zinc-600" strokeWidth={2.5} />
    );

  return (
    <div className="border-b border-zinc-800/40 py-1 last:border-none">
      <div className="flex items-center gap-2 text-[11px] font-mono">
        <span className="shrink-0">{icon}</span>
        <button
          onClick={onToggle}
          className="flex-1 bg-transparent text-left text-zinc-300 transition-colors hover:text-white"
        >
          {step.name}
        </button>
        <button
          onClick={onToggle}
          className="rounded p-1 text-zinc-500 transition-colors hover:bg-zinc-800/50 hover:text-zinc-300"
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="pb-1 pl-[22px] pt-1.5 text-[11px] leading-relaxed text-zinc-400">
              <div>{step.description}</div>
              {step.details && (
                <pre className="mt-1.5 overflow-x-auto rounded-md border border-zinc-800/60 bg-black/40 p-1.5 font-mono text-[10px] text-zinc-500">
                  {step.details}
                </pre>
              )}
              {step.error && <div className="mt-1 text-red-400">{step.error}</div>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function MsgBubble({ msg }: { msg: Message }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const isUser = msg.type === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}
    >
      <div
        className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded border text-[10px] font-bold ${
          isUser
            ? "border-blue-400/30 bg-gradient-to-br from-blue-500 to-indigo-600 text-white"
            : "border-teal-900/40 bg-gradient-to-br from-[#1c2c26] to-[#0f1a15] text-teal-500"
        }`}
      >
        {isUser ? "U" : <Bot size={13} />}
      </div>

      <div className={`flex max-w-[85%] flex-col ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-lg px-3 py-2.5 text-xs leading-[1.6] shadow-sm ${
            isUser
              ? "rounded-tr-sm border border-[#1a5580]/60 bg-[#0d3a5c]/80 text-[#b8d4f0]"
              : "rounded-tl-sm border border-zinc-800/80 bg-[#18181b]/90 text-zinc-200"
          }`}
        >
          <div className="whitespace-pre-wrap break-words">{msg.content}</div>
          {msg.steps && msg.steps.length > 0 && (
            <div className="mt-3 flex flex-col gap-0.5 border-t border-zinc-800/60 pt-2">
              {msg.steps.map((step) => (
                <StepRow
                  key={step.id}
                  step={step}
                  expanded={expanded === step.id}
                  onToggle={() => setExpanded(expanded === step.id ? null : step.id)}
                />
              ))}
            </div>
          )}
        </div>
        <div className="mt-1.5 px-1 text-[10px] font-medium tracking-wide text-zinc-600">
          {formatDate(msg.timestamp)}
        </div>
      </div>
    </motion.div>
  );
}

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
  return (
    <div
      className={`group relative flex h-7 items-center gap-2 border-l-2 px-3 transition-all ${
        isActive
          ? "border-blue-500 bg-[#27272a]/40 text-zinc-100"
          : "border-transparent text-zinc-400 hover:bg-[#18181b] hover:text-zinc-200"
      }`}
    >
      <button
        disabled={isSwitching}
        onClick={onSwitch}
        className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap bg-transparent py-1 text-left text-xs font-medium"
      >
        {session.title}
      </button>
      <span className="mr-1.5 shrink-0 font-mono text-[10px] text-zinc-600">
        {new Date(session.updatedAt).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })}
      </span>
      <button
        onClick={(event) => {
          event.stopPropagation();
          onDelete();
        }}
        title="Delete session"
        className="hidden h-5 w-5 shrink-0 items-center justify-center rounded border border-transparent p-0 text-zinc-500 transition-all hover:border-red-900/40 hover:bg-red-950/30 hover:text-red-400 group-hover:flex"
      >
        <Trash2 size={11} strokeWidth={2.5} />
      </button>
    </div>
  );
}

const MODE_CONFIG: Record<
  Mode,
  { icon: ReactNode; placeholder: string; statusPrefix: string }
> = {
  ask: {
    icon: <MessageCircle size={12} strokeWidth={2.5} />,
    placeholder: "Ask a question about your code...",
    statusPrefix: "Asking AI...",
  },
  agent: {
    icon: <Cpu size={12} strokeWidth={2.5} />,
    placeholder: "Ask agent to edit, create or fix files...",
    statusPrefix: "Agent running...",
  },
  plan: {
    icon: <ClipboardList size={12} strokeWidth={2.5} />,
    placeholder: "Describe what you want to plan or research...",
    statusPrefix: "Planning...",
  },
};

export default function ChatPanel() {
  const {
    messages,
    addMessage,
    replaceMessages,
    clearMessages,
    sessionId,
    activeFileId,
    tabs,
    settings,
    isRightPanelOpen,
    setSessionId,
    setStatusText,
    upsertTab,
    setFiles,
  } = useAppStore();

  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [switching, setSwitching] = useState(false);
  const [mode, setMode] = useState<Mode>("agent");
  const [confirmTarget, setConfirmTarget] = useState<SessionInfo | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const refreshSessions = async () => setSessions(await sessionsAPI.listSessions());

  useEffect(() => {
    void refreshSessions();
  }, [sessionId, messages.length]);

  const activeTab = tabs.find((tab) => tab.id === activeFileId);
  const modeConf = useMemo(() => MODE_CONFIG[mode], [mode]);

  if (!isRightPanelOpen) return null;

  const switchSession = async (id: string) => {
    if (!id || id === sessionId) return;
    setSwitching(true);
    try {
      replaceMessages(mapMsgs(await sessionsAPI.getMessages(id)));
      setSessionId(id);
      setStatusText("Session switched");
    } catch (error) {
      setStatusText(`Switch failed: ${error instanceof Error ? error.message : error}`);
    } finally {
      setSwitching(false);
    }
  };

  const newChat = async () => {
    try {
      const session = await sessionsAPI.createSession(
        `Chat ${new Date().toLocaleTimeString()}`
      );
      setSessionId(session.id);
      clearMessages();
      await refreshSessions();
      setStatusText("New chat started");
    } catch (error) {
      setStatusText(`Failed: ${error instanceof Error ? error.message : error}`);
    }
  };

  const executeDelete = async () => {
    if (!confirmTarget) return;
    const target = confirmTarget;
    setConfirmTarget(null);

    try {
      await sessionsAPI.deleteSession(target.id);
      const remaining = sessions.filter((session) => session.id !== target.id);
      setSessions(remaining);

      if (target.id === sessionId) {
        if (remaining[0]) {
          await switchSession(remaining[0].id);
        } else {
          const session = await sessionsAPI.createSession("New Chat");
          setSessionId(session.id);
          clearMessages();
          setSessions([session]);
        }
      }

      setStatusText(`Deleted "${target.title}"`);
    } catch (error) {
      setStatusText(`Delete failed: ${error instanceof Error ? error.message : error}`);
    }
  };

  const send = async () => {
    if (!input.trim()) return;

    const prompt = input;
    let currentSessionId = sessionId;

    if (!currentSessionId) {
      const session = await sessionsAPI.createSession(titleOf(prompt));
      currentSessionId = session.id;
      setSessionId(session.id);
      clearMessages();
      await refreshSessions();
    }

    addMessage({
      id: `u-${Date.now()}`,
      type: "user",
      content: prompt,
      timestamp: new Date(),
    });

    setInput("");
    setLoading(true);
    setStatusText(modeConf.statusPrefix);

    try {
      const response = await agentAPI.sendMessage(prompt, currentSessionId, {
        activeFilePath: activeTab?.path,
        provider: settings?.defaultProvider,
        mode,
      });

      setSessionId(response.sessionId);
      addMessage({
        id: `a-${Date.now()}`,
        type: "assistant",
        content: response.message,
        timestamp: new Date(),
        steps: response.steps,
      });

      if (response.filesModified.length > 0) {
        const files = await fileAPI.listFiles();
        setFiles(buildFileTree(files));

        for (const path of response.filesModified.slice(0, 6)) {
          const content = await fileAPI.readFile(path);
          const name = path.split("/").pop() ?? path;
          upsertTab({
            id: path,
            name,
            path,
            content,
            language: getLanguageFromFileName(name),
            isDirty: false,
          });
        }

        setStatusText(`Generated ${response.filesModified.length} files`);
      } else {
        setStatusText(mode === "plan" ? "Plan ready" : "Completed");
      }

      await refreshSessions();
    } catch (error) {
      addMessage({
        id: `err-${Date.now()}`,
        type: "assistant",
        content: `Error: ${error instanceof Error ? error.message : error}`,
        timestamp: new Date(),
      });
      setStatusText("Failed");
    } finally {
      setLoading(false);
    }
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

      <div className="z-10 flex w-[340px] shrink-0 flex-col border-l border-zinc-800/80 bg-[#0f0f11] shadow-[-4px_0_16px_rgba(0,0,0,0.3)] xl:w-[380px]">
        <div className="relative z-20 flex h-10 shrink-0 select-none items-center justify-between gap-2 border-b border-zinc-800/60 bg-zinc-900/60 px-4 text-[11px] font-bold uppercase tracking-widest text-zinc-500 shadow-sm backdrop-blur-sm">
          <Bot size={15} className="shrink-0 text-teal-500" strokeWidth={2.5} />
          <span className="mt-0.5 flex-1 text-zinc-300">AI Assistant</span>
          <button
            className="flex h-6 w-6 items-center justify-center rounded bg-transparent text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-white"
            onClick={() => void newChat()}
            title="New chat"
          >
            <MessageSquarePlus size={14} strokeWidth={2.5} />
          </button>
        </div>

        <div className="relative z-10 max-h-[140px] shrink-0 overflow-y-auto border-b border-zinc-800/60 bg-[#0f0f11] shadow-sm">
          {sessions.map((session) => (
            <SessionRow
              key={session.id}
              session={session}
              isActive={session.id === sessionId}
              isSwitching={switching}
              onSwitch={() => void switchSession(session.id)}
              onDelete={() => setConfirmTarget(session)}
            />
          ))}
          {sessions.length === 0 && (
            <div className="px-4 py-3 text-[11px] font-medium italic text-zinc-600">
              No sessions yet
            </div>
          )}
        </div>

        <div className="custom-scrollbar relative z-0 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-3.5 pb-4 pt-3">
          <AnimatePresence>
            {messages.length === 0 ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center text-sm text-zinc-500/70"
              >
                <Bot size={36} strokeWidth={1.5} className="mb-2 opacity-20" />
                <div className="font-medium tracking-wide">
                  {mode === "plan"
                    ? "Describe a system architecture or research topic to map out."
                    : mode === "ask"
                      ? "Ask any question about your codebase."
                      : "Describe what features you want me to write or modify."}
                </div>
              </motion.div>
            ) : (
              messages.map((message) => <MsgBubble key={message.id} msg={message} />)
            )}

            {loading && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex gap-2.5 px-1 py-1"
              >
                <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded border border-teal-900/40 bg-gradient-to-br from-[#1c2c26] to-[#0f1a15] text-teal-500 shadow-sm">
                  <Bot size={13} />
                </div>
                <div className="mt-0.5 flex h-8 items-center gap-1.5 rounded-lg rounded-tl-sm border border-zinc-800/80 bg-[#18181b]/90 px-3 py-2 shadow-sm">
                  <div className="h-1.5 w-1.5 animate-[bounce_1.4s_infinite_0s] rounded-full bg-zinc-500 opacity-70" />
                  <div className="h-1.5 w-1.5 animate-[bounce_1.4s_infinite_0.2s] rounded-full bg-zinc-500 opacity-70" />
                  <div className="h-1.5 w-1.5 animate-[bounce_1.4s_infinite_0.4s] rounded-full bg-zinc-500 opacity-70" />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
          <div ref={endRef} className="h-0 shrink-0" />
        </div>

        <div className="z-20 shrink-0 border-t border-zinc-800/80 bg-[#121214] pb-2 shadow-[0_-4px_16px_rgba(0,0,0,0.3)] backdrop-blur-md">
          <div className="flex items-center gap-1.5 px-3.5 pb-1 pt-3">
            {(["ask", "agent", "plan"] as const).map((item) => (
              <button
                key={item}
                className={`flex h-[24px] items-center gap-1.5 rounded border px-2.5 text-[11px] font-bold shadow-sm transition-all ${
                  mode === item
                    ? "border-zinc-600 bg-zinc-700/60 text-zinc-100"
                    : "border-transparent bg-transparent text-zinc-400 hover:bg-zinc-800 hover:text-white"
                }`}
                onClick={() => setMode(item)}
              >
                {MODE_CONFIG[item].icon}
                {item.charAt(0).toUpperCase() + item.slice(1)}
              </button>
            ))}
            <div className="ml-auto flex cursor-pointer items-center gap-1.5 rounded border border-zinc-800 bg-zinc-900/80 px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest text-zinc-400 shadow-inner transition-colors hover:border-blue-500/60 hover:text-zinc-200">
              <Bot size={11} className="text-teal-500" />
              {settings?.defaultProvider || "groq"}
              <ChevronDown size={11} strokeWidth={2.5} />
            </div>
          </div>

          <div className="px-3.5 py-1.5">
            <textarea
              rows={3}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
              placeholder={modeConf.placeholder}
              className="min-h-[60px] max-h-[160px] w-full resize-none rounded-md border border-zinc-700/80 bg-[#09090b] px-3 py-2 text-[13px] leading-relaxed text-white shadow-inner transition-colors placeholder:text-zinc-600 focus:border-blue-500/70 focus:bg-[#121214] focus:outline-none"
            />
          </div>

          <div className="flex items-center gap-2 px-3.5 pb-1">
            <button
              className="flex h-7 w-7 items-center justify-center rounded bg-transparent text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-white"
              title="Attach file"
            >
              <Paperclip size={14} strokeWidth={2} />
            </button>
            <button
              className="ml-auto flex h-7 items-center gap-2 rounded bg-blue-600 px-3.5 text-[11px] font-bold uppercase tracking-widest text-white shadow transition-transform hover:bg-blue-500 active:scale-95 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-600 disabled:shadow-none disabled:active:scale-100"
              onClick={() => void send()}
              disabled={!input.trim() || loading || switching}
            >
              <Send size={12} strokeWidth={2.5} />
              {mode === "plan" ? "Plan" : mode === "ask" ? "Ask" : "Send"}
            </button>
          </div>

          <div className="flex items-center gap-1.5 px-4 text-[10px] font-medium text-zinc-500/70">
            <kbd className="rounded-sm border border-zinc-700/50 bg-zinc-800/50 px-1 text-zinc-400 shadow-inner">
              Enter
            </kbd>
            to send
            <span className="px-1">·</span>
            <kbd className="rounded-sm border border-zinc-700/50 bg-zinc-800/50 px-1 text-zinc-400 shadow-inner">
              Shift + Enter
            </kbd>
            for newline
          </div>
        </div>
      </div>
    </>
  );
}
