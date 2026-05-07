# Telegram 文件转存 Bot 设计

## 目标

构建一个仅供单一所有者使用的 Telegram Bot。所有者将群组或频道中的文件消息转发给 Bot 后，Bot 自动将文件下载到服务器本地磁盘，并按日期目录保存，同时记录可审计的索引信息。

## 范围

本设计覆盖第一版最小可用产品：

- 单用户授权，只有指定 Telegram 用户 ID 可以触发下载
- 使用 Telegram Bot API 接收消息和获取文件下载地址
- 使用 long polling 运行，不使用 webhook
- 将文件保存到本地磁盘，按日期分目录
- 支持大文件流式下载，避免整文件进入内存
- 记录索引日志和运行日志
- 提供最小命令接口：`/start`、`/status`

本设计不包含：

- 多用户权限管理
- Web 管理界面
- 数据库存储
- 去重策略或自动清理策略
- 受保护转发内容的绕过方案

## 用户场景

所有者在 Telegram 中把普通群组或频道内的文件消息转发给 Bot。Bot 识别该消息中的文件，自动下载到服务器目录 `storage/YYYY-MM-DD/` 下，并回复保存结果。如果消息不含文件或发送者不是所有者，则拒绝处理。

## 架构

系统采用单进程结构：

1. Telegram 更新处理器通过 `python-telegram-bot` 使用 long polling 接收消息
2. 权限校验层只允许 `OWNER_TELEGRAM_USER_ID` 对象继续处理
3. 文件提取层从消息中识别可下载文件对象及其元数据
4. 下载层使用 `httpx` 对 Telegram 文件地址执行流式下载
5. 存储层负责目录创建、临时文件写入、原子重命名和重名处理
6. 索引层把归档结果追加到 `data/index.jsonl`
7. 日志层把运行事件写入 `logs/bot.log`

该架构保持为单进程串行下载，优先降低复杂度。并发配置预留，但第一版默认单文件串行处理。

## 技术选型

- Python 3.11+
- `python-telegram-bot`：Bot 更新接收与命令/消息处理
- `httpx`：可配置超时的流式下载
- `python-dotenv`：本地环境变量加载
- `logging`：标准库日志
- `systemd`：Linux 长期运行与开机自启

## 目录结构

建议项目结构如下：

```text
telegram-file-archive-bot/
  bot/
    __init__.py
    app.py
    config.py
    handlers.py
    downloader.py
    storage.py
    indexer.py
    logging_setup.py
    types.py
  data/
    index.jsonl
  logs/
    bot.log
  storage/
    2026-05-06/
  systemd/
    telegram-file-archive-bot.service
  tests/
    test_storage.py
    test_indexer.py
    test_handlers.py
  .env.example
  requirements.txt
  README.md
```

## 配置设计

通过环境变量提供以下配置：

- `BOT_TOKEN`：Telegram Bot Token
- `OWNER_TELEGRAM_USER_ID`：唯一允许使用 Bot 的用户 ID
- `STORAGE_ROOT`：文件存储根目录，默认 `./storage`
- `INDEX_FILE`：索引文件路径，默认 `./data/index.jsonl`
- `LOG_FILE`：日志文件路径，默认 `./logs/bot.log`
- `HTTP_TIMEOUT`：下载请求总读取超时，适合大文件场景
- `CHUNK_SIZE`：流式下载写盘块大小
- `MAX_CONCURRENT_DOWNLOADS`：预留并发数，第一版默认 `1`

配置加载失败时，应用应在启动阶段直接报错退出，而不是带着不完整配置运行。

## 消息与命令行为

### `/start`

返回 Bot 的用途说明、授权范围说明，以及当前存储根目录。

### `/status`

返回：

- 进程运行正常
- 当前存储根目录
- 当天已保存文件数

当天已保存文件数可以通过扫描索引文件中当天记录统计，第一版不需要额外状态存储。

### 文件转发消息

处理规则：

1. 校验发送者是否为所有者
2. 判断消息中是否携带可下载文件
3. 提取文件元数据
4. 创建当天目录
5. 执行流式下载
6. 写入索引
7. 回复成功消息，包含保存路径或文件名

### 非文件消息

回复“请转发带文件的消息”。

## 文件识别规则

第一版支持 Telegram 常见文件载体：

- `document`
- `video`
- `audio`
- `voice`
- `photo`（按最大分辨率项处理）

为了覆盖“群和频道里的文件”这个目标，处理逻辑应统一抽象为“从消息里提取一个可下载文件对象及推荐文件名”。若消息包含多个候选文件类型，优先顺序应明确且固定，避免行为歧义。

## 存储策略

### 日期目录

文件按接收当天日期保存到：

```text
storage/YYYY-MM-DD/
```

日期以服务器本地时区生成为准，便于你在服务器上直接按归档日期管理。

### 文件名

- 如果 Telegram 提供原始文件名，则优先保留
- 如果没有文件名，则生成 `file_<file_unique_id>`
- 如果发生重名，则追加随机短后缀，例如 `name__ab12cd.ext`

### 临时文件

下载过程中先写入 `.part` 文件，例如：

```text
storage/2026-05-06/movie.mp4.part
```

下载完成后执行原子重命名为正式文件名。这样即使中途失败，也不会留下看似完整的坏文件。

## 大文件下载设计

大文件支持是第一版核心要求，因此下载实现必须满足以下约束：

- 不将完整文件加载到内存
- 通过 `httpx` 流式读取响应体
- 按 `CHUNK_SIZE` 分块写入本地磁盘
- 为下载请求配置显式超时，避免默认超时过短导致大文件失败
- 下载过程中记录累计写入字节数，用于日志和错误定位
- 失败时删除 `.part` 文件

实现上，Bot 先通过 Telegram API 获取 `file_path`，再拼接为下载 URL，然后由独立下载模块执行流式落盘。

## 索引设计

每次成功保存文件后，在 `data/index.jsonl` 追加一行 JSON 记录。每条记录至少包含：

- `downloaded_at`
- `saved_path`
- `original_file_name`
- `saved_file_name`
- `file_size`
- `telegram_file_id`
- `telegram_file_unique_id`
- `source_chat_id`
- `source_chat_title`
- `source_chat_type`
- `forward_date`
- `sender_user_id`

选择 JSONL 而非数据库的原因：

- 追加写简单
- 便于审计
- 便于后续导入 SQLite 或其他存储
- 对单用户第一版已足够

## 权限控制

Bot 必须仅允许 `OWNER_TELEGRAM_USER_ID` 使用：

- 允许：所有者私聊 Bot 并转发文件
- 拒绝：任何其他用户的命令或消息

拒绝时应回复简短无状态错误，不透露服务器路径、配置或其他内部信息。

## 错误处理

必须显式处理以下错误：

- 配置缺失或格式错误
- 目标目录创建失败
- Telegram 文件元数据获取失败
- 下载超时
- 网络中断
- 本地磁盘写入失败
- 索引写入失败
- 不支持的消息类型

处理原则：

- 尽量给所有者返回可理解的错误消息
- 详细错误堆栈写入日志
- 临时文件必须清理
- 索引写入失败时，不删除已保存文件，但要明确记录“文件已保存、索引失败”的状态

## 日志设计

日志输出到 `logs/bot.log`，至少记录：

- 进程启动
- 配置摘要（不含敏感值）
- 收到授权用户消息
- 文件下载开始/完成/失败
- 已写入字节数和最终文件大小
- 索引写入结果
- 权限拒绝事件

日志级别至少使用 `INFO` 和 `ERROR`。

## 测试策略

第一版至少覆盖以下测试：

- 存储路径生成正确
- 重名文件自动加后缀
- 无文件名时自动生成文件名
- 索引记录写入为合法 JSONL
- 非所有者消息被拒绝
- 非文件消息返回提示
- 下载失败时删除 `.part` 文件

网络下载部分优先用 mock 或本地流对象测试，不依赖真实 Telegram 网络。

## 部署方式

第一版部署采用：

- Linux 服务器
- `.env` 配置
- `python -m bot.app` 启动
- `systemd` 托管进程

`systemd` 服务文件应设置：

- 自动重启
- 工作目录
- 环境文件路径
- 标准输出与错误输出进入 journald

## 兼容性与边界

该设计针对“普通群和频道中的普通可转发文件”场景。以下情况不保证成功：

- 受保护转发内容
- Telegram 平台限制导致 Bot 无法获取底层文件
- 超出服务器磁盘容量
- 长时间网络不稳定导致下载失败

如果未来主要来源转为受保护内容，则需要改用用户账号 API（MTProto）路线；这不在本设计范围内。

## 后续扩展点

以下扩展预留但不进入第一版实现：

- SQLite 索引
- 基于 `file_unique_id` 的去重模式
- 失败任务重试
- 下载队列和并发控制
- Web 检索界面
- 按来源或按类型分类存储

## 结论

第一版应保持为单用户、单进程、磁盘直存、JSONL 索引的最小可用实现。这样可以最快落地，并且已经满足“把频道和群里的文件转发给机器人，机器人下载到我的服务器里”的核心目标，同时通过流式下载满足大文件场景。
