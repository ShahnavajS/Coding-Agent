import { create } from "zustand";
import type {
  AppSettings,
  AppState,
  DiffViewerData,
  EditorTab,
  FileNode,
  Message,
} from "../types";

interface StoreActions {
  setFiles: (files: FileNode[]) => void;
  setSessionId: (sessionId: string) => void;
  setSettings: (settings: AppSettings) => void;
  setStatusText: (statusText: string) => void;
  setCurrentBranch: (branch: string) => void;
  upsertTab: (tab: EditorTab) => void;
  removeTab: (tabId: string) => void;
  setActiveTab: (tabId: string) => void;
  updateTab: (tabId: string, updates: Partial<EditorTab>) => void;
  addMessage: (message: Message) => void;
  replaceMessages: (messages: Message[]) => void;
  clearMessages: () => void;
  setDiffViewer: (data: DiffViewerData | null) => void;
  addTerminalOutput: (output: string) => void;
  clearTerminal: () => void;
  setTerminalRunning: (isRunning: boolean) => void;
  setTerminalApprovalRequired: (approvalRequired: boolean) => void;
  toggleLeftSidebar: () => void;
  toggleRightPanel: () => void;
  toggleBottomPanel: () => void;
  toggleSettings: () => void;
  setTheme: (theme: "dark" | "light") => void;
}

export const useAppStore = create<AppState & StoreActions>((set) => ({
  files: [],
  activeFileId: null,
  tabs: [],
  messages: [],
  diffViewer: null,
  terminal: {
    id: "main",
    output: [],
    isRunning: false,
    lastCommand: "",
    approvalRequired: false,
  },
  sessionId: null,
  settings: null,
  isLeftSidebarOpen: true,
  isRightPanelOpen: true,
  isBottomPanelOpen: true,
  isSettingsOpen: false,
  theme: "dark",
  statusText: "Booting backend...",
  currentBranch: "workspace",

  setFiles: (files) => set({ files }),
  setSessionId: (sessionId) => set({ sessionId }),
  setSettings: (settings) => set({ settings }),
  setStatusText: (statusText) => set({ statusText }),
  setCurrentBranch: (currentBranch) => set({ currentBranch }),
  upsertTab: (tab) =>
    set((state) => {
      const existing = state.tabs.find((current) => current.id === tab.id);
      if (existing) {
        return {
          tabs: state.tabs.map((current) =>
            current.id === tab.id ? { ...current, ...tab } : current
          ),
          activeFileId: tab.id,
        };
      }
      return {
        tabs: [...state.tabs, tab],
        activeFileId: tab.id,
      };
    }),
  removeTab: (tabId) =>
    set((state) => {
      const nextTabs = state.tabs.filter((tab) => tab.id !== tabId);
      return {
        tabs: nextTabs,
        activeFileId:
          state.activeFileId === tabId ? nextTabs[0]?.id ?? null : state.activeFileId,
      };
    }),
  setActiveTab: (tabId) => set({ activeFileId: tabId }),
  updateTab: (tabId, updates) =>
    set((state) => ({
      tabs: state.tabs.map((tab) =>
        tab.id === tabId ? { ...tab, ...updates } : tab
      ),
    })),
  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),
  replaceMessages: (messages) => set({ messages }),
  clearMessages: () => set({ messages: [] }),
  setDiffViewer: (diffViewer) => set({ diffViewer }),
  addTerminalOutput: (output) =>
    set((state) => ({
      terminal: {
        ...state.terminal,
        output: [...state.terminal.output, output],
      },
    })),
  clearTerminal: () =>
    set((state) => ({
      terminal: {
        ...state.terminal,
        output: [],
      },
    })),
  setTerminalRunning: (isRunning) =>
    set((state) => ({
      terminal: {
        ...state.terminal,
        isRunning,
      },
    })),
  setTerminalApprovalRequired: (approvalRequired) =>
    set((state) => ({
      terminal: {
        ...state.terminal,
        approvalRequired,
      },
    })),
  toggleLeftSidebar: () =>
    set((state) => ({ isLeftSidebarOpen: !state.isLeftSidebarOpen })),
  toggleRightPanel: () =>
    set((state) => ({ isRightPanelOpen: !state.isRightPanelOpen })),
  toggleBottomPanel: () =>
    set((state) => ({ isBottomPanelOpen: !state.isBottomPanelOpen })),
  toggleSettings: () =>
    set((state) => ({ isSettingsOpen: !state.isSettingsOpen })),
  setTheme: (theme) => set({ theme }),
}));
