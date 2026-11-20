# SeeU 业务图

> 编写:@Mr_Bingoo x Claude · 文中「作者」= @Mr_Bingoo
>
> 用图讲「有什么、怎么走」,文档讲「为什么、踩过什么坑」。图用 Mermaid 写:改一行字图就跟着变,GitHub 能直接显示。
> 一共五种:① 全景图(由哪些部分组成)② 能力矩阵(每类场景能做到什么程度)③ 泳道图(做一步时谁做什么、怎么判断、怎么返回,每种动作一张)
> ④ 状态图(会处在哪些状态、怎么切换)⑤ 思维导图(功能全貌)。
> 图只画 SeeU 通用的做法;某一步是作者在实际场景里碰到问题才加的,图下面用「实例:」一小段说明场景。

> 💡 标了「Windows 预览版」「Linux 预览版」的是这两个系统的图(全景图、能力矩阵各一份;泳道图 3.6、3.7 是 Windows,3.8、3.9 是 Linux);其余都按 Mac 版画,Windows 和 Linux 的差别见 [README](../README.md)。

## ① 全景图

**Mac 版**

```mermaid
block-beta
  columns 6
  H1["① 谁来调用"]:6
  U1["你的 Python 程序<br/>定时任务、自动化程序"]:2
  U2["AI(Claude、Codex、千问…)<br/>MCP 工具 + Skill 说明<br/>一键接入 · npx 启动包"]:2
  U3["命令行<br/>检查授权、取证、I See"]:2
  D1<["&nbsp;"]>(down):6
  H2["② SeeU"]:6
  J["判断<br/>入口:排路·换路·核实·回报<br/>安全底线 · 让路 · 借鼠标排队<br/>I See"]:2
  R["操作路线<br/>浏览器:插件/开关/辅助<br/>隐身浏览器 · 调试端口<br/>辅助功能 · 后台点击 · 借真鼠标"]:2
  FB["看画面与反馈<br/>截图 + 认字<br/>悬浮窗 · 灵动岛 · 代理光标<br/>光圈 · 提示条 · 检查授权 · 取证"]:2
  D2<["&nbsp;"]>(down):6
  H3["③ 靠的系统能力"]:6
  P1["辅助功能授权<br/>屏幕录制授权"]:2
  P3["后台点击私有接口<br/>失效退回真鼠标"]:2
  P4["AppleScript 按 App 授权<br/>调试端口(Chromium)"]:2
  D3<["&nbsp;"]>(down):6
  H4["④ 六类场景"]:6
  A1["Safari"] A2["Chrome 等"] A3["Electron App"] A4["原生 App"] A5["模拟器"] A6["iPhone 镜像"]
  classDef head fill:none,stroke:none,font-weight:bold
  class H1,H2,H3,H4 head
```

**Windows 预览版**

```mermaid
block-beta
  columns 6
  H1["① 谁来调用"]:6
  U1["你的 Python 程序<br/>定时任务、自动化程序"]:2
  U2["AI(Claude、Codex、千问…)<br/>MCP 工具 + Skill 说明<br/>一键接入 · npx 启动包"]:2
  U3["命令行<br/>检查、取证、设置"]:2
  D1<["&nbsp;"]>(down):6
  H2["② SeeU"]:6
  J["判断<br/>入口:排路·换路·核实·回报<br/>安全底线 · 让路 · 画面靠不住不按位置点<br/>I See"]:2
  R["操作路线<br/>后台浏览器(调试端口)<br/>读控件 · 发窗口消息<br/>借前台按下 · 借真鼠标"]:2
  FB["看画面与反馈<br/>截窗口 + 认字<br/>悬浮窗 · 灵动岛 · 代理光标<br/>提示条 · 检查 · 取证"]:2
  D2<["&nbsp;"]>(down):6
  H3["③ 靠的系统能力(不用开授权)"]:6
  P1["控件接口<br/>(UI Automation)"]:2
  P3["给窗口发鼠标键盘消息<br/>不行再借前台 / 真鼠标"]:2
  P4["截窗口 · Windows 自带认字<br/>调试端口(Chrome / Edge)"]:2
  D3<["&nbsp;"]>(down):6
  H4["④ 三类场景"]:6
  A1["原生 App"]:2 A2["Chrome / Edge 网页"]:2 A3["模拟器 · 自绘界面 App"]:2
  classDef head fill:none,stroke:none,font-weight:bold
  class H1,H2,H3,H4 head
```

**Linux 预览版**

```mermaid
block-beta
  columns 6
  H1["① 谁来调用"]:6
  U1["你的 Python 程序<br/>定时任务、自动化程序"]:2
  U2["AI(Claude Code、Codex、Cursor…)<br/>MCP 工具 + Skill 说明<br/>一键接入"]:2
  U3["命令行<br/>检查(能自动补)、设置、更新"]:2
  D1<["&nbsp;"]>(down):6
  H2["② SeeU"]:6
  J["判断<br/>入口:排路·换路·核实·回报<br/>安全底线(含锁屏、系统弹框)· 让路 · 排队<br/>I See"]:2
  R["操作路线<br/>后台浏览器(调试端口)<br/>按控件 · 菜单栏<br/>借真鼠标键盘"]:2
  FB["看画面与反馈<br/>截图 + 认字<br/>悬浮标 · 灵动岛 · 代理光标<br/>光圈 · 提示条 · 检查"]:2
  D2<["&nbsp;"]>(down):6
  H3["③ 靠的系统能力"]:6
  P1["辅助功能接口(AT-SPI)<br/>辅助功能总开关"]:2
  P3["系统截图授权<br/>系统远程操作授权"]:2
  P4["SeeU 的 GNOME 小插件<br/>调试端口(Chromium / Chrome)"]:2
  D3<["&nbsp;"]>(down):6
  H4["④ 三类场景"]:6
  A1["原生 App(GTK / Qt)"]:2 A2["Chromium / Chrome 网页"]:2 A3["模拟器 · 自绘界面 App"]:2
  classDef head fill:none,stroke:none,font-weight:bold
  class H1,H2,H3,H4 head
```

## ② 能力矩阵

图例:✅ 后台,不打扰 · ⚡ 会借一下前台或你的鼠标 · ⚠️ 有条件 · ❌ 做不到

**Mac 版**

| 场景 | 读内容 | 点 | 打字 | 滚动 | 藏起来也能干活 | 操作所需的授权 |
|---|---|---|---|---|---|---|
| Safari | ✅ | ✅ | ✅ | ✅ | ✅ 隐身 Safari | 辅助功能、Safari 开关(要输密码)、控制 Safari |
| Chrome 等 | ✅ | ✅ | ✅ | ✅ | ✅ 隐身 Chrome(启动闪 0.2~0.4 秒) | 辅助功能、插件或开关;隐身 Chrome 走调试端口,什么都不用开 |
| Electron App(用网页技术做的桌面软件,Electron、CEF 等都算;如 VS Code) | ✅ SeeU 单独打开的那份;⚠️ 你那份要窗口露着 | ✅ SeeU 单独打开的那份;⚠️ 你那份要窗口露着 | ✅ SeeU 单独打开的那份;⚠️ 你那份要窗口露着 | ✅ SeeU 单独打开的那份;⚠️ 你那份要窗口露着 | ✅ SeeU 单独打开的那份;❌ 你自己那份 | 单独打开的那份不用;你那份要辅助功能、屏幕录制 |
| 原生 App(备忘录…) | ✅ | ✅ | ✅ | ✅ | ✅(「打开某一条备忘录」会闪一下) | 辅助功能;用 AppleScript 时控制该 App |
| 模拟器(如 BlueStacks) | ✅ 认字 | ✅ 后台点(私有接口) | ✅ | ✅ | ❌(窗口要在) | 辅助功能、屏幕录制 |
| iPhone 镜像 | ✅ 认字 | ✅ 后台点(私有接口) | ✅ | ✅(卡住会补小拖动) | ❌(窗口要在,大小不限) | 辅助功能、屏幕录制 |
| 拖动(任何场景) | — | ⚡ 借真鼠标 | — | — | — | 同上 |

所有场景都先过安全底线:终端、系统权限弹窗、系统设置的「隐私与安全性」、存密码的 App(钥匙串、密码、1Password 等)、运行 SeeU 的 AI 客户端自己(如 Claude、Codex)、SeeU 自己的悬浮窗按钮(防 AI 自己打开 I See)、危险快捷键 / 命令 / 菜单一律拦;密码框、验证码框、银行卡框不碰。替千问后台打开 App 时,终端、能跑脚本的、存密码的、系统设置、浏览器、别的 AI 客户端和远程协助程序都不开。

「后台点(私有接口)」= 用 macOS 没公开的接口把点击直接投给窗口,系统升级可能失效,失效自动退回真鼠标(见 3.3)。

模拟器建议优先用 ADB(安卓官方的调试工具,公开接口,不经过 SeeU):点击、滑动、截图都完全后台、坐标准;SeeU 用后台点击补充,比如打中文(ADB 自带输入只支持英文和数字)、模拟器没开 ADB 的时候。

**Windows 预览版**

| 场景 | 读内容 | 点 | 打字 | 滚动 | 藏起来也能干活 | 操作所需的授权 |
|---|---|---|---|---|---|---|
| 原生 App(记事本、资源管理器…) | ✅ 读控件 | ✅ 后台点;⚡ 新式界面(如新版记事本的弹窗)借前台按一下 | ✅ | ✅ | ⚠️ 被别的窗口挡着行;最小化就看不到 | 不用 |
| Chrome / Edge 网页(后台浏览器) | ✅ | ✅ | ✅ | ✅ | ✅ 一直不出窗口;要登录时才叫出来让你自己登 | 不用;只碰允许名单里的网站 |
| 你自己开着的 Chrome、Electron App(如 VS Code) | ✅ 读控件 | ✅ 后台点 | ✅ 要先指定输入框 | ✅ | ❌ 窗口被挡着时网页里点不进(网页请用后台浏览器) | 不用 |
| 模拟器、自绘界面 App | ✅ 认字 | ✅ 后台点 | ✅ | ✅ | ❌(窗口要在,不能最小化) | 不用;认字要装 Windows 的文字识别语言包 |
| 拖动(任何场景) | — | ✅ 先试后台;⚡ 不行借真鼠标 | — | — | — | — |

Windows 上另外三条:以管理员身份运行的窗口碰不了(系统规定);窗口在别的虚拟桌面上时不借鼠标、不把你切过去;画面靠不住时(窗口被挡、机器很忙、在别的桌面)不照着截图上的位置点,改按控件点或请 AI 先再看一次。

**Linux 预览版**

| 场景 | 读内容 | 点 | 打字 | 滚动 | 藏起来也能干活 | 操作所需的授权 |
|---|---|---|---|---|---|---|
| 原生 App(文本编辑器、FeatherPad…) | ✅ 读控件 | ✅ 按控件点;⚡ 按屏幕位置点要借真鼠标 | ✅ | ✅ 有滚动条的;⚡ 没有的借鼠标 | ⚠️ 被挡着、最小化、在别的工作区也能按编号点,但截不到它的画面 | 辅助功能总开关、截图授权 |
| Chromium / Chrome 网页(后台浏览器) | ✅ | ✅ | ✅ | ✅ | ✅ 一直不出窗口;要登录时才叫出来让你自己登 | 不用;只碰允许名单里的网站 |
| VS Code 这类网页技术做的程序 | ✅ 读控件(VS Code 要带辅助功能参数启动) | ✅ 按控件点 | ⚡ 借键盘几秒 | ⚡ 借鼠标 | ❌ 要借键盘鼠标时,窗口得在当前工作区、没最小化 | 远程操作授权 |
| 你自己开着的浏览器(Firefox、Chrome…) | ✅ 只看 | ❌ | ❌ | ❌ | — | 不碰:会绕开允许名单、带着你的登录;网页走后台浏览器 |
| 模拟器、自绘界面 App | ✅ 认字(要装 Tesseract) | ⚡ 借真鼠标 | ⚡ 借键盘 | ⚡ 借鼠标 | ❌(窗口要露着) | 截图授权、远程操作授权 |
| 长按、拖动(任何场景) | — | ⚡ 借真鼠标 | — | — | — | 远程操作授权 |

Linux 上另外几条:只支持 GNOME 桌面(Wayland),SeeU 的 GNOME 小插件装上或更新后要注销重新登录一次;锁屏时什么都不做,系统弹框(输密码、授权)开着时不借你的鼠标键盘;按屏幕位置点时,那一点被别的窗口挡着就不点。

## ③ 泳道图

每张图一列一个模块,从上往下是时间。`alt` = 二选一的判断,`opt` = 满足条件才发生,`loop` = 重复(都有上限)。
「桌面反馈」那一列是你在屏幕上看到的东西;光圈要看悬浮窗上的「灯光」档位:关 / 抢占(只在借鼠标时亮橙色,默认)/ 被控(只要在操作就亮紫色)。
悬浮标平时只写「SeeU」,I See 开着时写「I See」(圆点呼吸 = 在干活);借鼠标、卡住不靠颜色,悬浮窗自己展开写清楚。

### 3.1 点一个按钮(原生 App)

```mermaid
sequenceDiagram
  autonumber
  participant U as 用户
  participant AI as AI / 项目
  participant E as SeeU 入口
  participant S as 安全·让路
  participant R as 操作路线
  participant A as 目标 App
  participant F as 桌面反馈
  AI->>E: 点某个按钮
  E->>F: 悬浮标「SeeU」呼吸,<br/>卡片写「正在点『确定』」<br/>(只有坐标时认点击处的字:<br/>点在字上照写,<br/>点在字旁边才写「正在点『确定』附近」)
  opt AI 调用时写了原因
    E->>F: 「正在…」下面灰字写原因,<br/>看画面时写在画面底部,<br/>3 秒淡出
  end
  E->>S: 安全底线检查
  alt 命中(终端、系统弹窗、<br/>运行 SeeU 的 AI 客户端自己…)
    S-->>E: 拒绝
    E-->>AI: refused「这一步请你自己来」
    AI-->>U: 转告
  else 通过
    E->>E: 按 App 类型排路<br/>(辅助功能 → 后台点击 → 借真鼠标)
    E->>R: 第 1 条:辅助功能按控件
    R->>A: 按下(不抢前台、不动鼠标)
    opt 灯光 = 被控
      F-->>U: 屏幕四周紫色光圈
    end
    F-->>U: 紫色代理光标「SeeU」移到按钮上
    E->>E: 读回 / 截图对比核实
    alt 生效
      E-->>AI: delivered
    else 没生效
      E->>R: 第 2 条:后台点击<br/>(点完截图对比,<br/>没变 = 记现场、换下一条)
      E->>R: 第 3 条:借真鼠标
      R->>S: 能借吗
      loop 你正在打字,<br/>或连续动鼠标键盘<br/>超过约 1.5 秒(有上限)
        S->>S: 等你停手约 3 秒
      end
      S->>S: 借鼠标排队<br/>(同一时间只让一个任务借真鼠标,<br/>别的任务在用就等,有上限)
      F-->>U: 悬浮窗自己展开:<br/>「正在用你的鼠标<br/>(点『确定』)/ 别动鼠标,<br/>几秒后还你」<br/>(多任务时排灵动岛最顶)
      F-->>U: 亮橙色代理光标,<br/>名牌写你设的署名
      opt 灯光 = 抢占或被控
        F-->>U: 屏幕四周橙色光圈
      end
      F->>F: 浮标先让开<br/>(这几秒不接鼠标)
      S->>S: 还盖着自家浮标就拒绝
      Note over S,F: 防 AI 点自家悬浮窗按钮、自己打开 I See
      S->>A: 切到前台,真鼠标点
      Note over U,S: 你中途连续动鼠标键盘超过约 1.5 秒 = 暂停,<br/>停手约 3 秒后自动继续。目标 App 弹着对话框时不点
      S->>A: 还原原来的前台和鼠标位置
      F-->>U: 借完 2.5 秒,<br/>展开的悬浮窗自己收回
      E->>E: 核实
      alt 成功
        E-->>AI: delivered
      else 还是不行
        F-->>U: 悬浮窗自己展开:「卡住了:<br/>原因 / 怎么办: …」,<br/>一直开着等你处理
        E-->>AI: 失败(卡在哪·原因·怎么办)
      end
    end
  end
```

你点开的悬浮窗一直开着,点收起才收;兜底 60 秒没动作缩回悬浮标,再 60 秒淡出。

**多个任务同时跑**

- SeeU 怎么做:
  - 同一个 App(Windows 上是同一个窗口)一次只让一个任务动手,做完一步留几秒给它接着做下一步;别的任务排队,最多等 30 秒,等不到就告诉 AI「忙,稍后再试」,不会硬插队。同一个 AI 客户端里的几个会话、Claude 和 Codex 这类不同客户端,都按这个排。
  - 打一长段字这类慢活,做的过程中一直报「还在做」,别人插不进来;因为别的任务刚动过这个 App 而被拦下、什么都没做的那一步,马上让出。
  - 按位置点的那一步要是排队超过 3 秒才轮到,而这期间窗口挪了、或点的地方附近画面变了,就不点,先让 AI 重新看一眼;别的任务动过同一个 App 的焦点,不指定输入框的打字、按键这次不做,让 AI 指定输入框(点框和打字连着做完,中间不让人插进来)。
  - 同一时间只让一个任务借真鼠标,别的任务排队等;借之前要是等过,等完再拍一张「动作前」的画面来比,不会把等的时候画面自己变了当成点成了。
  - 某个任务意外退出没放手,过一会儿自动作废,不会一直占着。
  - 每个任务一只自己的光标,名牌写着是哪个会话(Claude、Claude2…),颜色各不相同,排队的那只打瞌睡(Zz)、变淡;灵动岛上分两段,下段是排队中的。
- 建议:
  - 多个定时任务错开时间,尤其是要借鼠标的(拖动、后台点不进的);
  - 借鼠标多的任务安排在你不用电脑的时候跑;
  - 给 SeeU 单独留一个桌面,你在别的桌面干活,互不打扰;
  - 能走后台的都走后台(模拟器优先 ADB,Electron App 用 SeeU 单独打开的那份),借鼠标的次数越少越好。

实例:作者同时跑好几个自动化项目(手机 App、安卓模拟器、网页填表),为此自己写了一套跨项目的协作规则:谁在用鼠标、谁该让、定时任务怎么错开、程序崩了留下的占用怎么接管。上面的排队就是从这套规则里拿出来的最小部分。

### 3.2 打字

```mermaid
sequenceDiagram
  autonumber
  participant U as 用户
  participant AI as AI / 项目
  participant E as SeeU 入口
  participant S as 安全·让路
  participant R as 操作路线
  participant A as 目标 App
  participant F as 桌面反馈
  AI->>E: 往输入框打一段字<br/>(可带回车)
  E->>S: Mac 锁屏了吗 ·<br/>系统正在输密码吗 ·<br/>字里有危险命令吗 ·<br/>目标能碰吗
  alt 任一是
    E-->>AI: refused「这一步请你自己来」<br/>(锁屏时一律不打字,<br/>点击照常)
  else 都没有
    E->>F: 卡片写「正在往『搜索框』里打字」<br/>(『』里是输入框的名字,<br/>AI 写了原因就在下面灰字显示)
    E->>R: 第 1 条:后台打字
    R->>A: 只聚焦不置前,<br/>逐字发进目标进程<br/>(中英文都行)
    E->>E: 核实:读框里的字,<br/>读不到就截图认字,<br/>找最后几个字
    alt 打进去了
      opt 要回车
        E->>R: 单独按一次回车<br/>(免得半句话被发出去)
      end
      E-->>AI: delivered
    else 没打进去<br/>(模拟器不走这一步,直接报没生效)
      E->>R: 第 2 条:前台打字
      R->>S: 让路把关 + 借鼠标排队
      S->>A: 切到前台打字
      S->>A: 还原前台
      E-->>AI: 成功 / 没生效<br/>(交给调用方自己处理)
    end
  end
```

实例:作者在 BlueStacks(安卓模拟器)里测试时,打不进字是安卓里的输入连接断了,真键盘也打不进;窗口在别的桌面时切前台也只会白抢一次前台。所以模拟器不走前台打字,直接报没生效。

### 3.3 iPhone 镜像:后台点击和滚动(私有接口)

> **亮点**:镜像里点击、滚动用的是 macOS 没公开的 SkyLight 接口(`SLEventPostToPid`),把事件直接投给镜像窗口:**不动你的鼠标、不抢前台**。这是 SeeU 能在 iPhone 镜像、模拟器里真后台干活的关键。
> **⚠️ 提前知道**:① 系统升级可能改掉它 → 每次先查接口还在不在,不在就直接走真鼠标;② 投出去没有回执,不知道点没点进 → 靠截图对比核实,没变就记现场、退回真鼠标;
> ③ 找按钮靠截图认字,不依赖这个接口,失效了照常能用;④ 做法学自开源项目 Cua 的公开代码,不逆向任何闭源程序。

```mermaid
sequenceDiagram
  autonumber
  participant AI as AI / 项目
  participant E as SeeU 入口
  participant R as 后台点击
  participant M as iPhone 镜像
  participant S as 安全·让路
  participant F as 桌面反馈
  AI->>E: 点「确定」/ 在某处往下滚<br/>(可给一个空白点)
  E->>E: 只抓镜像窗口截图认字,<br/>找到「确定」在哪<br/>(公开接口,不算手机截屏)
  E->>R: 私有接口还在吗
  alt 不在(系统升级改掉了)
    R-->>E: 不可用
    E->>S: 直接走真鼠标<br/>(让路 + 借鼠标排队,<br/>见 3.1)
  else 在
    E->>F: 卡片写「正在点『确定』」<br/>(点在字旁边写「…附近」)<br/>/「正在往下滚」
    opt 你开着 Apps<br/>或 Spotlight<br/>(后台点击会把它们关掉)
      E->>E: 最多等 15 秒让你用完,<br/>超时照点并截图存下面板
    end
    R->>M: 先发一串「鼠标从窗外移进来」,<br/>让窗口知道指针在哪
    R->>M: 把点击 / 滚轮事件直接投给镜像进程<br/>(不动鼠标、不抢前台)
    Note over R,M: 投出去没有回执,收没收到只能看画面
    E->>E: 截图对比
    alt 画面变了
      E-->>AI: 成功
    else 没变 · 点击
      E->>E: 记现场(前后截图、<br/>点上是哪个窗口)
      E->>S: 退回真鼠标再点<br/>(让路 + 借鼠标排队)
      E-->>AI: 成功 / 失败(卡在哪·原因·<br/>怎么办)
    else 没变 · 刚点过后的第一次滚
      R->>M: 在空白点补一下小拖动解卡<br/>(不误点列表行)
      R->>M: 再滚一次
      E-->>AI: 滚动了 / 没动<br/>(调用方自己再决定)
    end
  end
```

拖动没有后台办法,一律借真鼠标(见 3.1)。

实例:作者用 iPhone 镜像操作某个 App 里的小程序页面(App 里内嵌的网页)时发现,后台点过一次之后,弹出面板会滚不动;上面「补一下小拖动」就是为它加的,落在列表空白处免得误点。
作者自己的自动化程序还要求镜像窗口固定成 391×859,所以打开了「固定尺寸」开关(`SEEU_BASELINE=1`);SeeU 默认不钉,窗口大小不限。

### 3.4 隐身浏览器干活,被叫出来

```mermaid
sequenceDiagram
  autonumber
  participant U as 用户
  participant AI as AI / 项目
  participant ST as 隐身浏览器
  participant W as 看门狗
  participant B as 浏览器
  participant F as 桌面反馈
  AI->>ST: 隐身拉起 Safari / Chrome 并打开页面
  alt 这个浏览器你正开着
    ST-->>AI: 不碰(只给 SeeU 用)
  else 没开着
    ST->>B: 拉起后马上藏起来<br/>(Safari 不露窗口,<br/>Chrome 露 0.2~0.4 秒)
    ST->>W: 开看门狗,<br/>每 0.3 秒看一眼窗口露没露
    loop 干活
      AI->>B: 读网页 / 点 / 填<br/>(Safari 走 Apple 事件开关,<br/>Chrome 走调试端口)
      F-->>U: 悬浮标只写 SeeU,<br/>卡片写「Safari 在后台隐身干活,<br/>别点开它」,看画面变灰
    end
    opt 你点了程序坞图标或「看画面」
      B-->>W: 窗口露出来了
      W->>W: 约 0.24 秒内发现,<br/>记下「被叫出来过」
      W->>F: 悬浮窗自己展开「卡住了:<br/>被叫到桌面上了 / 怎么办:<br/>一键重开」+ 提示条
      W->>W: 后台自动取证一次
      AI->>B: 再点 / 再打字
      W-->>AI: 一律拒绝(藏回去也不放行)
      U->>ST: 看完后运行一键重开
      ST->>B: 关掉 → 隐身重开 → 标签照原样开回来
      ST->>W: 新的看门狗
    end
    AI->>ST: 干完退出
  end
```

### 3.5 Electron App 走调试端口(以 VS Code 为例)

```mermaid
sequenceDiagram
  autonumber
  participant U as 用户
  participant AI as AI / 项目
  participant E as SeeU 入口
  participant C as 调试端口
  participant A as Electron App
  participant F as 桌面反馈
  AI->>E: 在 VS Code 里改一段字并保存
  alt 要改的是你自己开着的那份
    E->>A: 接不上调试端口,走老办法<br/>(辅助功能 → 后台打字)
    E->>A: 保存这类要借一下前台<br/>(见 3.1 让路)
    E-->>AI: 成功,<br/>并说明「这一步借了前台」
  else 交给 SeeU 独立干
    alt SeeU 单独打开的那份已经在跑
      E->>C: 直接接上
    else 还没开
      E->>C: 开 SeeU 单独打开的那份<br/>(单独配置,随机端口,<br/>只对本机开放)
      C->>A: 一出窗口就藏起来,<br/>前台还给你(可能闪一下)
    end
    F-->>U: 悬浮窗写「正在操作 VS Code」
    C->>A: 让页面以为自己有焦点
    alt 焦点在 VS Code 内置终端 / 要打危险命令
      C-->>E: 拒绝(安全底线)
      E-->>AI: refused「这一步请你自己来」
    else 正常
      C->>A: 读整个文件 / 写字 / 发 ⌘S 保存
      C->>C: 读回核实<br/>(有没有没保存的改动)
      C-->>E: 成功
      E-->>AI: delivered
    end
    opt 你点程序坞把它叫出来
      F-->>U: 0.2 秒内停手,<br/>悬浮窗自己展开说明 + 提示条
      U->>E: 看完运行一键重开<br/>(同样的文件)
    end
    E->>C: 干完关掉,端口跟着关
  end
```

### 3.6 Windows 预览版:点一个按钮

```mermaid
sequenceDiagram
  autonumber
  participant U as 用户
  participant AI as AI / 项目
  participant E as SeeU 入口
  participant S as 安全·让路
  participant R as 操作路线
  participant A as 目标窗口
  participant F as 桌面反馈
  AI->>E: 点某个按钮<br/>(编号 / 名字 / 屏幕位置)
  E->>F: 悬浮标「SeeU」呼吸,<br/>卡片写「正在点『确定』」
  E->>S: 安全底线检查
  alt 命中(管理员窗口、命令行窗口、<br/>密码 App、运行 SeeU 的 AI 客户端自己…)
    S-->>E: 拒绝
    E-->>AI: refused「这一步请你自己来」
    AI-->>U: 转告
  else 通过
    E->>E: 找目标:编号先核对控件还在不在<br/>(不在就不点,请 AI 先再看一次),<br/>名字先找控件,找不到再在认字结果里找
    opt 只有屏幕位置(或认字结果)
      E->>E: 画面靠得住吗<br/>(窗口被挡、机器很忙、在别的虚拟桌面)
      alt 靠不住
        E-->>AI: 不点,请改按编号或先再看一次
      end
    end
    F-->>U: 紫色代理光标移到按钮上
    E->>R: 第 1 档:后台点击
    R->>A: 给那一点下的子窗口发鼠标消息<br/>(不抢前台、不动鼠标)
    E->>E: 核实(画面、窗口标题、<br/>控件内容、读回的文字,<br/>任一变了就算生效)
    alt 生效
      E-->>AI: delivered
    else 没生效
      E->>S: 能往下借吗
      alt 窗口在别的虚拟桌面
        S-->>E: 不借、不把你切过去
        E-->>AI: refused「请你切过去,或把窗口挪过来」
      else 借用鼠标 = 关
        E-->>AI: 停下,说明卡在哪
      else 借用鼠标 = 问我
        F-->>U: 橙色提示条:要借一下
        E-->>AI: ask_user(你答应了 AI 再来一次)
      else 借用鼠标 = 开(默认)
        opt 这个控件能「按下」
          E->>R: 第 2 档:借前台按下
          R->>A: 拉到前台约 0.03~0.2 秒按下,<br/>马上把前台还你
        end
        E->>R: 第 3 档:借真鼠标
        R->>S: 你在用电脑吗
        loop 最近 1 秒动过鼠标键盘(最多等 6 秒)
          S->>S: 等你停手
        end
        alt 一直在用
          E-->>AI: refused「你正在用电脑,先不借」
        else 停手了
          F-->>U: 亮橙色代理光标
          R->>A: 拉到前台、核对那一点没被挡,<br/>真鼠标点(约 0.2 秒)
          R->>A: 鼠标放回原处,前台还给原来的程序
          E->>E: 核实
          E-->>AI: delivered,或失败(卡在哪·原因·怎么办)
        end
      end
    end
  end
```

跟 Mac(3.1)的主要不同:Windows 没有私有接口那一档,后台点击是给窗口发消息;中间多一档「借前台按下」,比借真鼠标快、不动鼠标;不用开任何系统授权。

### 3.7 Windows 预览版:网页走后台浏览器

```mermaid
sequenceDiagram
  autonumber
  participant U as 用户
  participant AI as AI / 项目
  participant E as SeeU 入口
  participant N as 允许名单
  participant B as 后台浏览器
  participant F as 桌面反馈
  AI->>E: 打开某个网页
  E->>N: 这个网站在名单里吗<br/>(I See 开着时不限)
  alt 不在
    E-->>AI: refused「不在允许名单」
    AI-->>U: 问你要不要加
    opt 你答应了
      AI->>N: 加进名单,再开一次
    end
  else 在
    alt 后台浏览器已经在跑
      E->>B: 直接接上
    else 还没开
      E->>B: 起一份 SeeU 专用的 Chrome 或 Edge<br/>(无界面、单独配置、随机端口,<br/>只对本机开放,不碰你自己的浏览器)
    end
    loop 干活
      AI->>E: 看网页 / 按编号点 / 填
      E->>B: 走调试端口
      alt 光标在密码框、验证码框、银行卡框
        B-->>E: 不打字、不按会改内容的键
        E-->>AI: refused「这一步请你自己来」
      else 正常
        B-->>E: 读回核实
        E-->>AI: delivered
      end
      F-->>U: 悬浮窗写正在操作网页,<br/>「看画面」变灰(没有窗口可看)
    end
    opt 网站要登录
      AI-->>U: 请你自己登
      U->>E: 同意叫出来
      E->>B: 关掉,开成普通窗口
      U->>B: 自己登录
      E->>B: 关掉窗口,无界面重开<br/>(登录留在这份配置里)
    end
  end
```

浏览器里不长按、不拖动(这两样按屏幕位置操作,会绕开允许名单),网页上的东西只按编号点。

### 3.8 Linux 预览版:点一个按钮、往框里写字

```mermaid
sequenceDiagram
  autonumber
  participant U as 用户
  participant AI as AI / 项目
  participant E as SeeU 入口
  participant S as 安全·让路
  participant R as 操作路线
  participant A as 目标窗口
  participant F as 桌面反馈
  AI->>E: 点某个按钮 / 往框里写字<br/>(编号 / 名字 / 屏幕位置)
  E->>F: 悬浮标「SeeU」呼吸,<br/>卡片写「正在点『确定』」
  E->>S: 安全底线检查
  alt 命中(终端、密码框、危险菜单如「运行」、<br/>运行 SeeU 的 AI 客户端自己、锁屏中…)
    S-->>E: 拒绝
    E-->>AI: refused「这一步请你自己来」
    AI-->>U: 转告
  else 通过
    E->>E: 找目标:回到上次看的那个窗口<br/>(同名的几个窗口不写错),<br/>编号先核对控件还在不在
    alt 按编号 / 名字,控件自己能按、框能写
      F-->>U: 紫色代理光标滑到目标
      E->>R: 第 1 档:按控件
      R->>A: 按控件自己的动作 / 往框里插字<br/>(不动鼠标键盘、不抢前台、被挡着也行)
      E->>E: 核实(控件、窗口标题变了,<br/>或读回的文字对上)
      E-->>AI: delivered
    else 只有屏幕位置,或后台做不到<br/>(VS Code 的输入框,模拟器)
      opt 只有屏幕位置
        E->>E: 那一点被别的窗口挡着吗
        alt 挡着
          E-->>AI: 不点,请改按编号或先再看一次
        end
      end
      E->>S: 能借吗
      alt 锁屏、系统弹框开着、<br/>窗口最小化或在别的工作区
        S-->>E: 不借
        E-->>AI: refused(写明原因)
      else 借用鼠标 = 关
        E-->>AI: 停下,说明卡在哪
      else 借用鼠标 = 问我
        F-->>U: 橙色提示条:要借一下
        E-->>AI: ask_user(你答应了 AI 再来一次)
      else 借用鼠标 = 开(默认)
        E->>S: 跟别的 SeeU 任务排队,一次一个
        R->>S: 系统远程操作授权<br/>(第一次弹框问你,之后免问)
        loop 最近 1 秒动过鼠标键盘(最多等 6 秒)
          S->>S: 等你停手
        end
        alt 一直在用
          E-->>AI: refused「你正在用电脑,先不借」
        else 停手了
          F-->>U: 橙色署名光标 + 屏幕四周橙色光圈,<br/>悬浮标写「正在用你的鼠标」
          R->>A: 拉到前台、挪指针,点 / 按键 / 打字<br/>(中文借剪贴板贴,贴完还原)
          R->>A: 指针放回原处,前台还给原来的程序
          E->>E: 核实
          E-->>AI: delivered,或失败(卡在哪·原因·怎么办)
        end
      end
    end
  end
```

跟 Windows(3.6)的主要不同:Linux 的后台只有「按控件」这一档(不能给窗口发鼠标消息),做不到就直接借真鼠标键盘;借之前要过系统的远程操作授权;锁屏、系统弹框开着时一律不借。

### 3.9 Linux 预览版:网页走后台浏览器

```mermaid
sequenceDiagram
  autonumber
  participant U as 用户
  participant AI as AI / 项目
  participant E as SeeU 入口
  participant N as 允许名单
  participant B as 后台浏览器
  participant F as 桌面反馈
  AI->>E: 打开某个网页
  E->>N: 这个网站在名单里吗<br/>(I See 开着时不限)
  alt 不在
    E-->>AI: refused「不在允许名单」
    AI-->>U: 问你要不要加
    opt 你答应了
      AI->>N: 加进名单,再开一次
    end
  else 在
    alt 后台浏览器已经在跑
      E->>B: 直接接上
    else 还没开
      E->>B: 起一份 SeeU 专用的 Chromium 或 Chrome<br/>(无界面、单独配置、随机端口,<br/>只对本机开放,不碰你自己的浏览器)
    end
    loop 干活
      AI->>E: 看网页 / 按编号点 / 填
      E->>B: 走调试端口
      alt 光标在密码框、验证码框、银行卡框
        B-->>E: 不打字、不按会改内容的键
        E-->>AI: refused「这一步请你自己来」
      else 正常
        B-->>E: 读回核实
        E-->>AI: delivered
      end
      F-->>U: 悬浮窗写正在操作网页,<br/>「看画面」变灰(没有窗口可看)
    end
    opt 网站要登录
      AI-->>U: 请你自己登
      U->>E: 同意叫出来
      E->>B: 关掉,开成普通窗口
      U->>B: 自己登录
      E->>B: 关掉窗口,无界面重开<br/>(登录留在这份配置里)
    end
  end
```

跟 Windows(3.7)一样;不同只在浏览器:Linux 用 Chromium 或 Chrome(Ubuntu 上 snap 版 Chromium 也行)。你自己开着的浏览器 SeeU 只看不动(点、打字、按键、滚动都拒),网页一律交给这份后台浏览器。

## ④ 状态图

### 4.1 隐身浏览器

```mermaid
stateDiagram-v2
  NotOpen: 没开着
  Hidden: 藏着干活
  Out: 被叫出来
  Stopped: 停手
  [*] --> NotOpen
  NotOpen --> Hidden: 隐身拉起(你自己开着就不碰)
  Hidden --> Hidden: 读 / 点 / 打字
  Hidden --> Out: 你点了程序坞图标或看画面
  Out --> Stopped: 约 0.24 秒内发现,悬浮窗展开说明 + 提示条 + 取证
  Stopped --> Stopped: 再操作一律拒绝(藏回去也不放行)
  Stopped --> Hidden: 你运行一键重开(标签照原样)
  Hidden --> NotOpen: 干完退出
```

### 4.2 悬浮窗

```mermaid
stateDiagram-v2
  None: 不显示
  Badge: 悬浮标
  Win: 悬浮窗
  Borrow: 借鼠标展开
  Stuck: 卡住展开
  Island: 灵动岛
  [*] --> None
  None --> Badge: SeeU 开始动手(每次从悬浮标开始,不记上次)
  Badge --> Win: 你点开
  Win --> Badge: 你点收起,或 60 秒没动作
  Badge --> None: 再 60 秒没动作,淡出
  Badge --> Borrow: 借真鼠标
  Borrow --> Badge: 还回去 2.5 秒后自己收回
  Badge --> Stuck: 某一步卡住
  Stuck --> Badge: 你点收起(不会自己收)
  state Win {
    Live: 看画面
    Steps: 看操作
    [*] --> Live
    Live --> Steps: 点「看操作」(隐身浏览器只有这个)
    Steps --> Live: 点「看画面」
  }
  Badge --> Island: 两个以上任务同时在跑(位置跟悬浮标共用)
  Island --> Badge: 只剩一个
  note right of Badge
    平时只写「SeeU」,I See 开着时写「I See」
    圆点颜色 = 当前模式(紫 = 后台,橙 = 借鼠标,可在设置里改),呼吸 = 在干活
  end note
  note left of Win
    AI 在用时:「正在…」下面灰字写原因
    按钮栏多一个「原因」开关(默认开)
  end note
  note right of Island
    点开每个任务一行
    排序:借鼠标 > 卡住 > 最近有动作
  end note
```

### 4.3 I See(我知风险,授权先做再说)

```mermaid
stateDiagram-v2
  Off: 关
  On: 开
  [*] --> Off
  Off --> On: 你亲手点悬浮窗按钮(SeeU 不点自己,AI 不替你开)/ 你自己用命令行打开
  On --> Off: 你关掉
  On --> Off: 默认 24 小时到期自动关(浏览器额外权限还开着就提醒你关)
  state On {
    Work: 干活
    Try: 换办法
    Skip: 跳过
    Halt: 卡住
    [*] --> Work
    Work --> Try: 遇到问题不停下问你
    Try --> Work: 换通了(每处最多 3 条路 / 60 秒)
    Try --> Skip: 做不了,后面不靠它(记一笔,最后汇报)
    Skip --> Work
    Try --> Halt: 后面都靠它(立刻停下报告)
  }
  note right of Off
    关着时做不到就直接报告
    卡在哪、原因、怎么办
    只管网页操作;让路、密码框、安全底线开了也照样有效
  end note
```

## ⑤ 思维导图

SeeU 能做的全部事情,一张图看完。

```mermaid
mindmap
  root((SeeU))
    看
      截图认字
      辅助功能读控件
      网页元素清单
    做
      点 · 长按
      打字 · 按键 · 菜单
      滚动 · 卡住补拖
      拖动要借鼠标
    六类场景
      Safari
      Chrome 等浏览器
      Electron App
      原生 App
      模拟器
      iPhone 镜像
    不打扰你
      后台点击 · 不抢前台
      让路 · 借鼠标排队
      几个 AI 一起用 · 同 App 轮流
      隐身浏览器
      调试端口
    让你看得见
      悬浮窗 · 悬浮标
      灵动岛 · 多任务
      代理光标 · 光圈
      提示条
      AI 写的原因
      借鼠标一律提示
    守底线
      安全底线写死
      密码 App 不碰
      不点自己的浮标
      AI 规矩:不替你提交和付款
      I See 我知风险
    出事有据
      检查授权
      一键取证
      被叫出来就停手
    谁来用
      Python 程序
      AI · MCP 加 Skill
      一键接入 Claude、Codex 等五家 · 手动接千问等
      命令行
```
