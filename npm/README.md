# seeu-computeruse (launcher)

A tiny launcher for **[SeeU](https://github.com/Mr-Bingoo/seeu-computeruse)** — background Computer Use for your Mac (Windows preview).

Some AI apps only accept MCP servers started with `npx` (for example **Qwen / 千问** desktop 5.2+, on Mac and Windows). This package lets them start the SeeU you have already installed. It has no dependencies and downloads nothing else.

1. Install SeeU and [Node.js](https://nodejs.org) first (see the [README](https://github.com/Mr-Bingoo/seeu-computeruse/blob/main/README.en.md#install)), then run once: `python3 -m seeu install qianwen` (Windows: `python -m seeu install qianwen`).
2. In the AI app, add an MCP server — name `seeu`, type STDIO, command:

```
npx -y seeu-computeruse
```

3. On the Mac, grant the AI app (e.g. 千问) Accessibility and Screen & System Audio Recording, then quit and reopen it.

Tips for Qwen: if the first try shows "connection failed" or nothing happens, restart Qwen and open the Connections page again. On Windows, the installer on Qwen's site is an older build: click "New version" at the top right (maybe twice) and restart until "Daily / Work" appears.

在千问里：左上切到「工作」→「连接」→「+ 添加」→「手动填写配置」，名称填 `seeu`，类型选 STDIO，命令填 `npx -y seeu-computeruse`。第一次加常显示「连接失败」，重启千问再看就好；Windows 版要先在右上「新版本」升级到有「工作」页的版本。

MIT · @Mr_Bingoo
