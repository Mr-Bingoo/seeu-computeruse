# 更新说明

中文 | [English](CHANGELOG.en.md)

每一版写几句大白话 : 加了什么、改了什么、要不要你做点什么。更新用 `python3 -m seeu update`，查自己是哪一版用 `python3 -m seeu version`。

## v1.0.0(2026-11-02)

第一个公开版本。

- **后台操作** : 原生 App、Safari / Chrome 网页、用网页技术做的 App、iPhone 镜像、安卓模拟器，都能在后台看画面、点击、打字、滚动，不抢你的鼠标、不切你的前台窗口。
- **看得见** : 紫色代理鼠标 + 悬浮标，点开能看操作步骤和实时画面，随时叫停。
- **接入** : 支持 MCP 和技能(Skill)，`python3 -m seeu install auto` 一键接 Claude、Codex、Cursor、Trae、VS Code。
- **安全底线写死在代码里** : 不碰终端、密码和隐私设置，不替你提交、付款、发消息。
- **借用鼠标三档** : 开(默认，先提醒)/ 问我 / 关。
- **只支持 macOS** : Windows、Linux 版本正在调研中。
