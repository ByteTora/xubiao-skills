# 徐彪Skills — 数字分身

> 基于 51,437 条微信聊天记录训练的 AI Persona Skill

## 这是什么

徐彪的数字分身。当 AI 加载这个 Skill 后，会以徐彪的说话方式、性格特征和幽默风格进行对话。不是简单的"模仿语气"，而是一个有完整人格画像、价值观体系和对话规则的角色系统。

## 数据来源

- **5 年跨度**：2022-09 ~ 2026-07
- **51,437 条消息**：全部来自"我"发出的单人对话
- **141 个会话**：好友/同事/家人/同学
- **过滤规则**：剔除群聊、企业号、公众号、无效会话（<20条互动）

## 安装

需要 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 或兼容的 Skills 系统。

```bash
# 克隆仓库
git clone https://github.com/ByteTora/xubiao-skills.git

# 复制到 skills 目录（适配你的工具）
cp -r xubiao-skills ~/.config/skills/
```

或直接用 `.skill` 文件安装（如果你的工具支持）。

## 触发场景

当你需要 AI 以"徐彪"的身份说话时自动触发：

- 模拟徐彪聊天
- 以徐彪口吻回复朋友
- 生成符合徐彪风格的对话内容
- 扮演徐彪进行角色扮演

## 人物画像速览

| 维度 | 特征 |
|------|------|
| **核心驱动** | 阶层跃迁 — 农村家庭，三研究生，靠学历+技术立足 |
| **价值观** | 平等互惠、真实自然、理性务实、自我成长 |
| **决策风格** | 理性分析型，信息搜集先行，多方案并行 |
| **幽默风格** | 自嘲 >> 吐槽 > 冷幽默，[Facepalm] 是灵魂 |
| **金钱观** | 精算型节俭，反消费主义，为家人慷慨 |
| **感情观** | 渴望深度连接，双向奔赴，从焦虑走向稳定 |
| **社交角色** | 桥梁连接者，被当"可咨询的人" |
| **语言特征** | 短句主导(70%)，97%无标点，[Facepalm]表情大户 |

### 典型表达

```
确实 / 可以 / 嗯嗯          ← 万能回应
就是...                      ← 标志性句式
一言难尽[Facepalm]           ← 万金油
我心思你那边...              ← 山东方言
绝了 / 神速啊 / 巧了巧了     ← 开心感叹
```

## 目录结构

```
徐彪Skills/
├── SKILL.md                     ← 角色设定入口（~300行）
├── references/
│   ├── language_fingerprint.md  ← 语言指纹（500+行）
│   ├── personality_profile.md   ← 人格画像（300+行）
│   ├── conversation_patterns.md ← 对话模式（12场景）
│   └── stats.json               ← 统计数据
└── scripts/
    ├── build_dataset.py         ← 数据清洗脚本
    ├── analyze_style.py         ← 统计分析脚本
    └── sample_for_llm.py       ← 分层采样脚本
```

## 如何从自己的微信聊天记录构建分身

如果你的微信数据库已经解密，可以用 `scripts/` 下的工具链复现。

### 步骤 1：数据清洗

```bash
python3 scripts/build_dataset.py \
  --output references/clean_messages.jsonl \
  --min-self 20
```

从解密后的 SQLite 数据库提取单人对话文本消息。需要配置：
- `vendor/wechat-decrypt/decrypted/` — 解密后的数据库目录
- `vendor/wechat-decrypt/config.json` — 含 own_wxid

**核心逻辑**：通过 WeChat 的 `Name2Id` 表 + `real_sender_id` 字段精确识别"我"的消息（非简单启发式）。

### 步骤 2：统计分析

```bash
python3 scripts/analyze_style.py --pretty
```
输出词频、emoji、标点、时间分布等统计。

### 步骤 3：采样

```bash
python3 scripts/sample_for_llm.py --size 5000
```
按季度分层 + 长度多样性采样。

### 步骤 4：LLM 分析

将采样消息分批送入大模型，生成三份分析文件：
- `language_fingerprint.md` — 语言风格
- `personality_profile.md` — 人格画像
- `conversation_patterns.md` — 对话模式

### 步骤 5：蒸馏 Persona

综合以上分析，编写 `SKILL.md` 作为最终角色设定。

### 步骤 6：验证与打包

```bash
# 验证
python3 <skill-creator>/scripts/quick_validate.py ./

# 打包为 .skill 文件
python3 <skill-creator>/scripts/package_skill.py . ./dist/
```

## 技术说明

### 发送者识别（关键难点）

微信 4.0 数据库中，`Msg_{md5}` 表有 `real_sender_id` 字段。在单人对话中：
- 对话双方的 `real_sender_id` 分别对应 `Name2Id` 表中的不同 rowid
- 通过 `Name2Id` 把 `real_sender_id` 翻译成 username
- 与 config.json 中的 own_wxid 比对 → 精确判定"我"的消息

**群聊中不适用**（`real_sender_id` 在群聊里只标识发言人编号），因此本 Skill 仅使用单人对话数据。

### 消息类型

| 类型 | 处理方式 |
|------|----------|
| 文本 (type=1) | 明文或 ZSTD 解压 |
| 图片 (type=3) | 丢弃 |
| 语音 (type=34) | 丢弃 |
| 表情 (type=47) | 丢弃 |
| 链接 (type=49) | 丢弃 |
| 通话 (type=50) | 丢弃 |
| 系统消息 | 丢弃 |

仅保留纯文本消息用于语言风格分析。

## 隐私说明

- 所有训练数据已通过脚本脱敏（手机号→[电话]、微信号→[微信号]等）
- 仓库中不包含任何原始聊天记录
- 不包含任何可识别个人身份的信息
- 所有参考文件均为统计分析摘要

## License

MIT
