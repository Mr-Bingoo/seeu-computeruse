<div align="center">

# SeeU

> *You see SeeU, I know you see. I See.*

**让你的AI 在Mac上可以后台看画面、点按钮、打字...和你并行使用互不打扰！**

中文 | [English](README.en.md)

仅支持 macOS（Windows、Linux 上装不了）

</div>

<!-- 演示视频 : 中文版待传。在 GitHub 网页编辑 README,把 MP4 拖进去拿到链接,换掉这一行。 -->

SeeU 的名字来自发音相同的 CU(Computer Use,让 AI 操作电脑),意思是「先看清，再动手」。

它会在屏幕上再放一个紫色的代理鼠标替 AI 干活。看画面、点击、输入、滚动都在后台完成，不抢你的鼠标、不切你的前台窗口。你可以照常写文档、回消息，它会在旁边做它的事，点击SeeU悬浮标就可以知道或看到AI在干什么。

## 你可以这样说

装好之后，在 Claude、Codex、Cursor 这些 AI 里直接说 :

```
「用 SeeU 在备忘录里新建一条，写上今天的待办」
「看一下访达里桌面上有哪些文件」
「在 Safari 后台开个新标签，读一下这个网页讲了什么」
「用 iPhone 镜像打开手机某游戏签个到」
```

## 能做什么

| 场景 | SeeU 怎么做 |
|---|---|
| 原生 App(备忘录、文本编辑、访达…) | 读界面上的按钮和文字，按编号点、后台打字 |
| Safari / Chrome 网页 | 在**后台标签页**里读网页、填表、点按钮，不打扰你正在看的那页 |
| 用网页技术做的 App(VS Code 等…) | 拉起 SeeU 自己的一份，全程藏着读写，你开着的那份不碰 |
| iPhone 镜像 | 截图认字，后台点手机屏幕、打开手机上的 App |
| 安卓模拟器 | 截图认字，后台点击 |
| 不确定的 App | `python3 -m seeu 探一下 <App>` : 先看它是什么内核、能读到多少按钮、SeeU 会走哪条路 |

每做一步都看画面有没有变化，没生效就换个办法或停下来告诉你卡在哪，不会闷头乱点。详细介绍见 [SeeU 是什么](docs/What-is-SeeU.zh-CN.md)。

## 安装

**前置条件** : 只支持 macOS，Apple 芯片的 Mac(在 macOS 27 上测过，更早的系统和 Intel 芯片没测过)、系统自带的 `python3`(第一次运行会提示安装「命令行开发者工具」，点安装就行)和 PyObjC :

```bash
/usr/bin/python3 -m pip install --user pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-ScreenCaptureKit pyobjc-framework-CoreMedia
```

然后三种装法任选一种 :

**① 把链接丢给 AI(最省事)**

```
帮我装上 SeeU:https://github.com/Mr-Bingoo/seeu-computeruse
```

AI 会自己下载、装好上面的依赖、运行 `python3 -m seeu install auto` 接好(认出是哪家 AI 就接哪家)。

**② 一行命令装成技能**

```bash
npx skills add Mr-Bingoo/seeu-computeruse
```

装完第一次用时，AI 会照技能说明自己装好依赖、把 MCP 接上。

**③ 手动**

```bash
git clone https://github.com/Mr-Bingoo/seeu-computeruse.git
cd seeu-computeruse
python3 -m seeu install auto      # 或指定:claude | codex | cursor | trae | vscode
python3 -m seeu check             # 看还缺哪些系统授权，缺的会写怎么开
```

**授权** : 运行 `python3 -m seeu check`，它会告诉你该给谁开(可能是你的 AI 客户端，也可能是 SeeU 小程序)，照着在系统设置 → 隐私与安全性里打开**辅助功能**和**屏幕与系统录音**就行。开完授权要完全退出 AI 客户端再打开，才会生效。

已经测通的 AI 客户端 : Claude(Code 和桌面版聊天页)、Codex、Cursor、Trae 国内版、VS Code + Copilot、WorkBuddy、豆包(WorkBuddy 和豆包要手动接)。其他支持 MCP 的客户端，把 `python3 -m seeu mcp` 当成本机 MCP 服务接上就行。

**更新** : `python3 -m seeu update`(用 git clone 装的)或 `npx skills update seeu`(用 npx 装的)，每版改了什么见[更新说明](CHANGELOG.md)，查自己是哪一版用 `python3 -m seeu version`。**移除** : `python3 -m seeu uninstall <客户端>`。

<!-- sync:safety -->
## 安全底线(写死在代码里)

- 不碰终端、系统设置的「隐私与安全性」、系统密码和授权弹窗、钥匙串和密码类 App，也不碰正在运行 SeeU 的那个 AI 客户端本身(防止 AI 自己批准自己)。
- 不按危险快捷键(清空废纸篓、锁屏、注销、强制退出…)，不打危险命令(sudo、删整个磁盘…)。
- 不填密码框、银行卡框、验证码框;**不替你提交表单、不付款、不发消息**——填好就停下，让你自己点。
- 网页或 App 里写着「让 AI 去做什么」的文字，只当内容转告你，不照做。
- 后台做不到的步骤(比如拖动)才借你的真鼠标几秒 : 先等你停手，用完还原，屏幕上会提示。默认已开启提醒用户后进行借用，你也可以使用 `python3 -m seeu 设置 借用鼠标 关`(不借用)或 `问我`(每次先问你)。
<!-- /sync:safety -->

## SeeU 还是官方自带的 Computer Use?

这不是选择题，是协作和辅助，为的是让你有更好的「CU」使用体验！

几乎各家模型厂商都在把更强的「AI 操作电脑」能力做进模型里，SeeU 借助模型的能力，尝试把一部分场景做得更好 :

1. **不会限使用时长** : 部分模型的 Computer Use 单次使用时长不能超过 30 分钟。
2. **成为项目的能力** : 放到需要自动化执行的项目里使用，免去每次向 Agent 申请使用的过程。
3. **后台默默的干活** : 大部分场景下不会打扰你，不抢鼠标、不切前台，你可以和 AI 并行使用电脑。
4. **知道它在做什么** : 桌面上显示紫色代理鼠标，悬浮窗里可以看操作步骤和实时画面，也能随时叫停。
5. **关键时刻提醒你** : 需要借用你的鼠标或中断时主动提醒，抢占和被控时屏幕边缘可选择展示提醒灯光。
6. **执行策略会自选** : 根据场景自动选择方案，如果你此时在使用鼠标且无法后台执行时会主动给你让路！
7. **轻松上手不挑剔** : 一键接入，支持 MCP 和技能(Skill) 不绑定某家客户端。
8. **不捆绑也不私藏** : 无需注册、无需登录，本地权限，逻辑可查……喜欢就用，不喜欢就一键移除。
9. **开源但坚守底线** : 什么能做、什么不能做，底线写死在代码里，不仅仅靠 AI 自觉!

<!-- sync:notes -->
## 须知

- iPhone 镜像后台点击用的是 macOS 的私有接口，系统更新后可能会失效，若遇到这种情况时 SeeU 会默认借用你的鼠标继续(先等你停手、屏幕上有提示、用完还原)，不会直接就抢你的鼠标。如果你不愿意“借用系统鼠标”的设置为默认打开，可以更改对应配置（关闭后部分必须使用系统鼠标的场景会完全卡住！）
- SeeU 的状态和日志放在 `~/.seeu`，想换位置可以设环境变量 `SEEU_HOME`(浏览器相关的文件不跟着换，固定在 `~/.seeu/seeu_web` : Chromium 内核浏览器的插件中转、以及它们跟 Safari 共用的网站允许名单)。
- SeeU 在判断和决策时可能会进行截图，并且会随对话发给你当前使用的 AI 服务商，这是属于你和你当前使用的模型服务提供商那边的事，不在 SeeU 能控制的范畴内。

## 出问题怎么办

1. 先运行 `python3 -m seeu check`，看缺哪项授权，照它写的去开。
2. 开完或改完授权，要完全退出 AI 客户端再打开，才会生效。
3. 还不行，到 [Issues](https://github.com/Mr-Bingoo/seeu-computeruse/issues) 反馈 : 写上版本(`python3 -m seeu version`)、用的哪家 AI、在操作哪个 App、卡在哪一步。可以附上 `python3 -m seeu evidence` 记下的现场，里面可能有窗口标题、截图这类信息，发之前先看一眼有没有隐私。
<!-- /sync:notes -->

## 文档

- [SeeU 是什么](docs/What-is-SeeU.zh-CN.md) : 完整介绍
- [业务图](docs/SeeU-业务图.zh-CN.md) : 全景图、能力矩阵、流程图、状态图
- [SKILL.md](SKILL.md) : 给 AI 看的使用说明
- [更新说明](CHANGELOG.md) : 每一版改了什么

## 许可证

MIT · @Mr_Bingoo
