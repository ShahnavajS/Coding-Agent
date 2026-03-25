export interface FileNode {
  id: string;
  name: string;
  type: "file" | "folder";
  path: string;
  size?: number;
  children?: FileNode[];
  isOpen?: boolean;
}

export interface EditorTab {
  id: string;
  name: string;
  path: string;
  content: string;
  language: string;
  isDirty: boolean;
}

export interface AgentStep {
  id: string;
  name: string;
  status: "pending" | "in-progress" | "completed" | "failed";
  description: string;
  details?: string;
  error?: string;
}

export interface ToolUsage {
  toolName: string;
  description: string;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  status: "pending" | "completed" | "failed";
}

export interface Message {
  id: string;
  type: "user" | "assistant";
  content: string;
  timestamp: Date;
  steps?: AgentStep[];
  toolUsage?: ToolUsage[];
}

export interface DiffViewerData {
  isOpen: boolean;
  diffId: string;
  originalContent: string;
  modifiedContent: string;
  fileName: string;
  validation?: {
    ok: boolean;
    language: string;
    parser: string;
    messages: string[];
  };
  onAccept?: () => void;
  onReject?: () => void;
}

export interface TerminalSession {
  id: string;
  output: string[];
  isRunning: boolean;
  lastCommand: string;
  approvalRequired?: boolean;
}

export interface ProviderSettings {
  model: string;
  baseUrl?: string;
  apiKeyEnv?: string;
  modelPath?: string;
  enabled: boolean;
  configured: boolean;
  available?: boolean;
  reason?: string;
}

export interface AppSettings {
  workspacePath: string;
  backendHost: string;
  backendPort: number;
  corsOrigins: string[];
  defaultProvider: string;
  shellTimeoutSeconds: number;
  providers: Record<string, ProviderSettings>;
}

export interface SessionInfo {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export interface AppState {
  files: FileNode[];
  activeFileId: string | null;
  tabs: EditorTab[];
  messages: Message[];
  diffViewer: DiffViewerData | null;
  terminal: TerminalSession;
  sessionId: string | null;
  settings: AppSettings | null;
  isLeftSidebarOpen: boolean;
  isRightPanelOpen: boolean;
  isBottomPanelOpen: boolean;
  isSettingsOpen: boolean;
  theme: "dark" | "light";
  statusText: string;
  currentBranch: string;
}

export interface AIAgentResponse {
  message: string;
  steps: AgentStep[];
  filesModified: string[];
  sessionId: string;
}

declare global {
  interface Window {
    desktopBridge: {
      getMeta: () => Promise<any>;
      selectFolder: () => Promise<string | null>;
      onBackendLog: (callback: (message: string) => void) => () => void;
    };
  }
}
