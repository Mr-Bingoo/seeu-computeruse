# SeeU 业务图

> 编写:@Mr_Bingoo x Claude · 文中「作者」= @Mr_Bingoo
>
> 用图讲「有什么、怎么走」,文档讲「为什么、踩过什么坑」。图用 Mermaid 写:改一行字图就跟着变,GitHub 能直接显示。
> 一共六种:① 全景图(由哪些部分组成)② 能力矩阵(每类场景能做到什么程度)③ 泳道图(做一步时谁做什么、怎么判断、怎么返回,每种动作一张)
> ④ 状态图(会处在哪些状态、怎么切换)⑤ 思维导图(功能全貌)。
> 图只画 SeeU 通用的做法;某一步是作者在实际场景里碰到问题才加的,图下面用「实例:」一小段说明场景。

## ① 全景图

```mermaid
block-beta
  columns 6
  H1["① 谁来调用"]:6
  U1["你的 Python 程序<br/>定时任务、自动化程序"]:2
  U2["AI(Claude、Codex…)<br/>MCP 工具 + Skill 说明<br/>一键接入"]:2
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

## ② 能力矩阵

图例:✅ 后台,不打扰 · ⚡ 会借一下前台或你的鼠标 · ⚠️ 有条件 · ❌ 做不到

| 场景 | 读内容 | 点 | 打字 | 滚动 | 藏起来也能干活 | 操作所需的授权 |
|---|---|---|---|---|---|---|
| Safari | ✅ | ✅ | ✅ | ✅ | ✅ 隐身 Safari | 辅助功能、Safari 开关(要输密码)、控制 Safari |
| Chrome 等 | ✅ | ✅ | ✅ | ✅ | ✅ 隐身 Chrome(启动闪 0.2~0.4 秒) | 辅助功能、插件或开关;隐身 Chrome 走调试端口,什么都不用开 |
| Electron App(用网页技术做的桌面软件,Electron、CEF 等都算;如 VS Code) | ✅ SeeU 专用那份;⚠️ 你那份要窗口露着 | ✅ SeeU 专用那份;⚠️ 你那份要窗口露着 | ✅ SeeU 专用那份;⚠️ 你那份要窗口露着 | ✅ SeeU 专用那份;⚠️ 你那份要窗口露着 | ✅ SeeU 专用那份;❌ 你自己那份 | 专用那份不用;你那份要辅助功能、屏幕录制 |
| 原生 App(备忘录…) | ✅ | ✅ | ✅ | ✅ | ✅(「打开某一条备忘录」会闪一下) | 辅助功能;用 AppleScript 时控制该 App |
| 模拟器(如 BlueStacks) | ✅ 认字 | ✅ 后台点(私有接口) | ✅ | ✅ | ❌(窗口要在) | 辅助功能、屏幕录制 |
| iPhone 镜像 | ✅ 认字 | ✅ 后台点(私有接口) | ✅ | ✅(卡住会补小拖动) | ❌(窗口要在,大小不限) | 辅助功能、屏幕录制 |
| 拖动(任何场景) | — | ⚡ 借真鼠标 | — | — | — | 同上 |

所有场景都先过安全底线:终端、系统权限弹窗、系统设置的「隐私与安全性」、存密码的 App(钥匙串、密码、1Password 等)、运行 SeeU 的 AI 客户端自己(如 Claude、Codex)、SeeU 自己的悬浮窗按钮(防 AI 自己打开 I See)、危险快捷键 / 命令 / 菜单一律拦;密码框、验证码框、银行卡框不碰。

「后台点(私有接口)」= 用 macOS 没公开的接口把点击直接投给窗口,系统升级可能失效,失效自动退回真鼠标(见 3.3)。

模拟器建议优先用 ADB(安卓官方的调试工具,公开接口,不经过 SeeU):点击、滑动、截图都完全后台、坐标准;SeeU 用后台点击补充,比如打中文(ADB 自带输入只支持英文和数字)、模拟器没开 ADB 的时候。

## ③ 泳道图

每张图一列一个模块,从上往下是时间。`alt` = 二选一的判断,`opt` = 满足条件才发生,`loop` = 重复(都有上限)。
「桌面反馈」那一列是你在屏幕上看到的东西;光圈要看悬浮窗上的「灯光」档位:关 / 抢占(只在借鼠标时亮橙色,默认)/ 被控(只要在操作就亮紫色)。
悬浮标任何时候只写「SeeU」(圆点呼吸 = 在干活);借鼠标、卡住不靠颜色,悬浮窗自己展开写清楚。

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
  Note over E,F: 你点开的悬浮窗一直开着,点收起才收,<br/>兜底 60 秒没动作缩回悬浮标,再 60 秒淡出
```

**多个任务同时跑**

- SeeU 怎么做:同一时间只让一个任务借真鼠标,别的任务排队等;等的时间有上限,等不到就报「卡住」,不会硬抢。某个任务意外退出没放手,过一会儿自动作废,不会一直占着。
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
  Note over AI,M: 拖动没有后台办法,一律借真鼠标(见 3.1)
```

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
    alt SeeU 专用那份已经在跑
      E->>C: 直接接上
    else 还没开
      E->>C: 开 SeeU 专用那份<br/>(单独配置,随机端口,<br/>只对本机开放)
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
    任何时候只写「SeeU」
    圆点颜色 = 你设置的颜色,呼吸 = 在干活
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
      不替你提交和付款
      I See 我知风险
    出事有据
      检查授权
      一键取证
      被叫出来就停手
    谁来用
      Python 程序
      AI · MCP 加 Skill
      一键接入 Claude 和 Codex
      命令行
```
