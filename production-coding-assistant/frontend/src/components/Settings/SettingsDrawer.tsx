import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Save, TriangleAlert, X } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { settingsAPI } from "../../utils/api";

function statusTone(configured: boolean, available?: boolean) {
  if (!configured) return "text-accent-red";
  if (available === false) return "text-accent-yellow";
  return "text-accent-green";
}

export default function SettingsDrawer() {
  const { isSettingsOpen, toggleSettings, settings, setSettings, setStatusText } =
    useAppStore();
  const [defaultProvider, setDefaultProvider] = useState("ollama");
  const [shellTimeout, setShellTimeout] = useState(30);

  useEffect(() => {
    if (!settings) return;
    setDefaultProvider(settings.defaultProvider);
    setShellTimeout(settings.shellTimeoutSeconds);
  }, [settings]);

  useEffect(() => {
    if (!isSettingsOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isSettingsOpen]);

  const providerEntries = useMemo(
    () => Object.entries(settings?.providers || {}),
    [settings]
  );

  if (!settings || !isSettingsOpen) return null;

  const handleSave = async () => {
    try {
      const nextSettings = await settingsAPI.save({
        defaultProvider,
        shellTimeoutSeconds: shellTimeout,
      });
      setSettings(nextSettings);
      setStatusText(`Saved settings | provider=${nextSettings.defaultProvider}`);
      toggleSettings();
    } catch (error) {
      setStatusText(
        `Settings save failed: ${
          error instanceof Error ? error.message : "Unknown error"
        }`
      );
    }
  };

  return createPortal(
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[9999] isolate bg-black/65 backdrop-blur-sm"
        onClick={toggleSettings}
      >
        <motion.aside
          initial={{ x: 520, opacity: 0.6 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 520, opacity: 0.6 }}
          transition={{ type: "spring", stiffness: 260, damping: 28 }}
          onClick={(event) => event.stopPropagation()}
          className="absolute right-0 top-0 flex h-full w-full max-w-[34rem] flex-col border-l border-dark-border bg-dark-surface shadow-2xl"
        >
          <div className="border-b border-dark-border px-6 py-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-mono text-gray-100">Settings</h2>
                <p className="mt-1 text-sm text-gray-400">
                  Provider routing, model fallbacks, and runtime defaults.
                </p>
              </div>
              <button
                onClick={toggleSettings}
                className="rounded-sm p-2 transition-colors hover:bg-dark-hover"
              >
                <X size={18} className="text-gray-400" />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5">
            <div className="space-y-6">
              <section className="rounded-md border border-dark-border bg-dark-bg/70 p-4">
                <div className="mb-4">
                  <div className="text-xs uppercase tracking-wide text-gray-500">
                    Default Provider
                  </div>
                  <p className="mt-1 text-sm text-gray-400">
                    Choose the preferred provider. If it fails, the backend now tries
                    healthy configured fallbacks automatically.
                  </p>
                </div>
                <select
                  value={defaultProvider}
                  onChange={(event) => setDefaultProvider(event.target.value)}
                  className="w-full rounded-sm border border-dark-border bg-dark-surface px-3 py-3 text-sm text-gray-100 outline-none transition-colors focus:border-accent-blue"
                >
                  {providerEntries.map(([providerName, provider]) => (
                    <option key={providerName} value={providerName}>
                      {providerName} | {provider.model} |{" "}
                      {provider.available ? "ready" : provider.configured ? "configured" : "missing setup"}
                    </option>
                  ))}
                </select>
              </section>

              <section className="rounded-md border border-dark-border bg-dark-bg/70 p-4">
                <div className="mb-4 text-xs uppercase tracking-wide text-gray-500">
                  Shell Timeout
                </div>
                <input
                  type="number"
                  value={shellTimeout}
                  min={5}
                  max={300}
                  onChange={(event) => setShellTimeout(Number(event.target.value))}
                  className="w-full rounded-sm border border-dark-border bg-dark-surface px-3 py-3 text-sm text-gray-100 outline-none transition-colors focus:border-accent-blue"
                />
              </section>

              <section className="rounded-md border border-dark-border bg-dark-bg/70 p-4">
                <div className="mb-4">
                  <div className="text-xs uppercase tracking-wide text-gray-500">
                    Provider Health
                  </div>
                  <p className="mt-1 text-sm text-gray-400">
                    This shows what the app can actually use right now.
                  </p>
                </div>

                <div className="space-y-3">
                  {providerEntries.map(([providerName, provider]) => {
                    const tone = statusTone(provider.configured, provider.available);
                    const isHealthy = provider.configured && provider.available !== false;

                    return (
                      <div
                        key={providerName}
                        className="rounded-sm border border-dark-border bg-dark-surface p-3"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="font-mono text-sm text-gray-100">
                              {providerName}
                            </div>
                            <div className="mt-1 text-sm text-gray-300">
                              model: {provider.model || "not set"}
                            </div>
                            {provider.baseUrl && (
                              <div className="break-all text-sm text-gray-400">
                                base URL: {provider.baseUrl}
                              </div>
                            )}
                            {provider.apiKeyEnv && (
                              <div className="text-sm text-gray-400">
                                env key: {provider.apiKeyEnv}
                              </div>
                            )}
                            {provider.modelPath && (
                              <div className="break-all text-sm text-gray-400">
                                model path: {provider.modelPath}
                              </div>
                            )}
                            {provider.reason && (
                              <div className="mt-2 text-sm text-gray-500">
                                {provider.reason}
                              </div>
                            )}
                          </div>

                          <div className={`flex items-center gap-2 text-sm ${tone}`}>
                            {isHealthy ? (
                              <CheckCircle2 size={16} />
                            ) : (
                              <TriangleAlert size={16} />
                            )}
                            <span className="font-mono">
                              {!provider.configured
                                ? "missing setup"
                                : provider.available === false
                                  ? "unavailable"
                                  : "ready"}
                            </span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            </div>
          </div>

          <div className="flex items-center justify-end gap-2 border-t border-dark-border px-6 py-4">
            <button onClick={toggleSettings} className="button-secondary">
              Cancel
            </button>
            <button
              onClick={() => void handleSave()}
              className="button-primary flex items-center gap-2"
            >
              <Save size={14} />
              Save Settings
            </button>
          </div>
        </motion.aside>
      </motion.div>
    </AnimatePresence>,
    document.body
  );
}
