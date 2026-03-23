import type { AppSettings, SessionInfo } from "../types";

const API_BASE_URL =
  (import.meta.env.VITE_API_URL as string) || "http://localhost:5000/api";

interface APIResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface FileInfo {
  path: string;
  name: string;
  type: "file" | "folder";
  size?: number;
}

export interface AgentResponse {
  message: string;
  steps: Array<{
    id: string;
    name: string;
    status: "completed" | "in-progress" | "failed" | "pending";
    description: string;
    details?: string;
  }>;
  filesModified: string[];
  sessionId: string;
  providerStatus?: {
    used: boolean;
    provider: string;
    model?: string;
    error?: string;
  };
  diffPreview?: DiffPreview;
}

export interface TerminalOutput {
  stdout: string;
  stderr: string;
  exitCode: number | null;
  requiresApproval?: boolean;
  risk?: string;
  success?: boolean;
}

export interface DiffPreview {
  id: string;
  path: string;
  originalContent: string;
  modifiedContent: string;
  createdAt: string;
  validation: {
    ok: boolean;
    language: string;
    parser: string;
    messages: string[];
  };
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<APIResponse<T>> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = (await response.json()) as APIResponse<T>;
  if (!response.ok) {
    throw new Error(payload.error || payload.message || "Request failed");
  }
  return payload;
}

export const fileAPI = {
  listFiles: async (): Promise<FileInfo[]> => {
    const data = await request<FileInfo[]>("/files/list", { method: "GET" });
    return data.data || [];
  },

  readFile: async (path: string): Promise<string> => {
    const data = await request<{ path: string; content: string }>("/files/read", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    return data.data?.content || "";
  },

  deleteFile: async (path: string): Promise<boolean> => {
    const data = await request<void>("/files/delete", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    return data.success;
  },

  createPath: async (
    path: string,
    type: "file" | "folder",
    content = ""
  ): Promise<{ path: string; type: "file" | "folder"; size?: number }> => {
    const data = await request<{ path: string; type: "file" | "folder"; size?: number }>(
      "/files/create",
      {
        method: "POST",
        body: JSON.stringify({ path, type, content }),
      }
    );
    if (!data.data) {
      throw new Error("No create result returned");
    }
    return data.data;
  },

  previewWrite: async (path: string, content: string): Promise<DiffPreview> => {
    const data = await request<DiffPreview>("/diff/preview", {
      method: "POST",
      body: JSON.stringify({ path, content }),
    });
    if (!data.data) {
      throw new Error("No diff preview returned");
    }
    return data.data;
  },

  applyDiff: async (diffId: string): Promise<{
    path: string;
    checkpoint: { id: string };
    validation: DiffPreview["validation"];
  }> => {
    const data = await request<{
      path: string;
      checkpoint: { id: string };
      validation: DiffPreview["validation"];
    }>("/diff/apply", {
      method: "POST",
      body: JSON.stringify({ diffId }),
    });
    if (!data.data) {
      throw new Error("No diff apply result returned");
    }
    return data.data;
  },
};

export const sessionsAPI = {
  createSession: async (title?: string): Promise<SessionInfo> => {
    const data = await request<SessionInfo>("/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
    if (!data.data) {
      throw new Error("No session returned");
    }
    return data.data;
  },
  listSessions: async (): Promise<SessionInfo[]> => {
    const data = await request<SessionInfo[]>("/sessions", { method: "GET" });
    return data.data || [];
  },
  getMessages: async (sessionId: string) => {
    const data = await request<
      Array<{
        id: string;
        role: string;
        content: string;
        createdAt: string;
        metadata?: Record<string, unknown>;
      }>
    >(`/sessions/${sessionId}/messages`, { method: "GET" });
    return data.data || [];
  },
  deleteSession: async (sessionId: string): Promise<boolean> => {
    const data = await request<{ id: string }>(`/sessions/${sessionId}`, {
      method: "DELETE",
    });
    return data.success;
  },
};

export const agentAPI = {
  sendMessage: async (
    message: string,
    sessionId: string | null,
    context?: Record<string, unknown>
  ): Promise<AgentResponse> => {
    const data = await request<AgentResponse>("/agent/ask", {
      method: "POST",
      body: JSON.stringify({ message, sessionId, context }),
    });
    if (!data.data) {
      throw new Error("No agent response returned");
    }
    return data.data;
  },

  getStatus: async (): Promise<{
    status: string;
    busy: boolean;
    architecture?: string;
  }> => {
    const data = await request<{
      status: string;
      busy: boolean;
      architecture?: string;
    }>("/agent/status", {
      method: "GET",
    });
    return data.data || { status: "unknown", busy: false };
  },
};

export const terminalAPI = {
  executeCommand: async (
    command: string,
    approved = false
  ): Promise<TerminalOutput> => {
    const data = await request<TerminalOutput>("/terminal/execute", {
      method: "POST",
      body: JSON.stringify({ command, approved }),
    });
    return (
      data.data || {
        stdout: "",
        stderr: "Command execution failed",
        exitCode: 1,
      }
    );
  },
};

export const settingsAPI = {
  get: async (): Promise<AppSettings> => {
    const data = await request<AppSettings>("/settings", { method: "GET" });
    if (!data.data) {
      throw new Error("No settings returned");
    }
    return data.data;
  },
  save: async (settings: Partial<AppSettings>): Promise<AppSettings> => {
    const data = await request<AppSettings>("/settings", {
      method: "POST",
      body: JSON.stringify(settings),
    });
    if (!data.data) {
      throw new Error("No settings returned");
    }
    return data.data;
  },
};

export const gitAPI = {
  getStatus: async (): Promise<{ branch: string; dirty: boolean }> => {
    return { branch: "workspace", dirty: false };
  },
};

export const healthCheck = async (): Promise<boolean> => {
  try {
    const res = await fetch(`${API_BASE_URL}/health`, { method: "GET" });
    return res.ok;
  } catch {
    return false;
  }
};
