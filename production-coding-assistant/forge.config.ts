import type { ForgeConfig } from "@electron-forge/shared-types";
import { MakerSquirrel } from "@electron-forge/maker-squirrel";
import { MakerZIP }      from "@electron-forge/maker-zip";
import { MakerDeb }      from "@electron-forge/maker-deb";
import { MakerRpm }      from "@electron-forge/maker-rpm";
import { VitePlugin }    from "@electron-forge/plugin-vite";
import path              from "node:path";

const config: ForgeConfig = {
  packagerConfig: {
    name:           "Production Coding Assistant",
    executableName: "production-coding-assistant",
    appVersion:     "0.1.0",
    appCopyright:   `Copyright © ${new Date().getFullYear()} sanus`,
    // Use your custom icon if present; Electron Forge handles .ico/.icns/.png per platform
    icon: path.join(__dirname, "desktop", "icons", "app"),
    // Embed the Python backend into the packaged app
    extraResource: ["backend"],
    // Let the Vite plugin keep only the packaged `.vite` output.
    prune: false,
  },

  // This app does not ship native Node add-ons, so skip rebuild work.
  rebuildConfig: {
    types: [],
  },

  makers: [
    new MakerSquirrel({
      name:                 "production_coding_assistant",
      setupExe:             "ProductionCodingAssistant-Setup.exe",
      setupIcon:            path.join(__dirname, "desktop", "icons", "app.ico"),
      noMsi:                true,
    }),
    new MakerZIP({}, ["darwin"]),
    new MakerDeb({
      options: {
        name:        "production-coding-assistant",
        productName: "Production Coding Assistant",
        categories:  ["Development"],
      },
    }),
    new MakerRpm({
      options: {
        name:        "production-coding-assistant",
        productName: "Production Coding Assistant",
      },
    }),
  ],

  plugins: [
    new VitePlugin({
      build: [
        {
          entry:  "desktop/electron/main.ts",
          config: "desktop/vite.main.config.ts",
          target: "main",
        },
        {
          entry:  "desktop/electron/preload.ts",
          config: "desktop/vite.preload.config.ts",
          target: "preload",
        },
      ],
      renderer: [
        {
          name:   "main_window",
          config: "frontend/vite.config.ts",
        },
      ],
    }),
  ],
};

export default config;
