# 使用指南

本指南面向日常使用，覆盖启动、对话、计划、任务图与常见问题。

## 1) 快速启动

后端：

```bash
pip install -r requirements.txt
./start_backend.sh
```

前端：

```bash
cd web-ui
npm install
npm run dev
```

默认前端会连接 `ENV.API_BASE_URL` 指定的后端地址；需要时可在 `.env` 中配置。

## 2) 左侧导航与侧边栏

- 左侧导航（Dashboard / AI Chat / Task Management 等）支持折叠按钮收缩/展开。
- AI Chat 页面左侧会话列表支持搜索、选择模式与批量删除。

## 3) 对话（Chat）

### 新建/切换会话

- 点击 `New Conversation` 新建会话。
![21b9ea0ceb36c24f704f574ffb4714ca](https://cdn.jsdelivr.net/gh/AllenYGY/ImageSpace@main/uPic/21b9ea0ceb36c24f704f574ffb4714ca.png)
- 点击会话条目切换历史会话（首次会拉取历史消息）。
![6e61e4c278cc3ac88cd96f474a23b4db](https://cdn.jsdelivr.net/gh/AllenYGY/ImageSpace@main/uPic/6e61e4c278cc3ac88cd96f474a23b4db.png)

### 重命名/自动标题

- 会话菜单中可手动 **Rename**。
![0369c2f7b39d6653838fa8b9893ade60](https://cdn.jsdelivr.net/gh/AllenYGY/ImageSpace@main/uPic/0369c2f7b39d6653838fa8b9893ade60.png)
- **Regenerate title** 会重新生成标题。
![4a1f41dfd8419679134e9703ecdba747](https://cdn.jsdelivr.net/gh/AllenYGY/ImageSpace@main/uPic/4a1f41dfd8419679134e9703ecdba747.png)

### 归档与恢复

- 菜单中可 **Archive conversation**。
![8a40c29fc647c0251109dae7ea4eaf33](https://cdn.jsdelivr.net/gh/AllenYGY/ImageSpace@main/uPic/8a40c29fc647c0251109dae7ea4eaf33.png)  
- 顶部 `Archived only` 开关可仅显示已归档会话。
- 已归档会话支持 **Restore conversation** 取消归档。

### 批量删除

- 点击 `Select` 进入选择模式。
- 支持 `Select all` 全选当前筛选结果。
- 点击 `Delete selected` 批量删除。

### 导出对话

- 会话菜单中选择 `Export conversation`。
![fca0dacd683d2f4bab4a570a2acb7582](https://cdn.jsdelivr.net/gh/AllenYGY/ImageSpace@main/uPic/fca0dacd683d2f4bab4a570a2acb7582.png)
- 支持多种格式导出（Markdown / JSON / Text）。

## 4) Web Search 选择

输入框右侧可选搜索提供方：

- `Built-in search`
- `Perplexity search`

如使用 Perplexity，需配置 `PERPLEXITY_API_KEY`以便访问。

## 5) 计划与任务

### 创建计划

在对话中输入类似“创建计划”的意图的指令即可触发计划创建。

计划创建与分解为异步流程，界面会提示 **Plan creation in progress**，
任务图与计划页会自动刷新，任务生成后会逐步显示。

### 任务图（右侧 Task Graph）

- 显示计划树结构（可折叠子节点）。
- 点击节点会打开任务详情抽屉。
![0b8011e44a22c9fd6080df6db13a27b2](https://cdn.jsdelivr.net/gh/AllenYGY/ImageSpace@main/uPic/0b8011e44a22c9fd6080df6db13a27b2.png)
![b679b5891d97b12bddd853c8676f89dc](https://cdn.jsdelivr.net/gh/AllenYGY/ImageSpace@main/uPic/b679b5891d97b12bddd853c8676f89dc.png)
- 创建/分解期间会自动刷新。

### 计划

- 支持导出当前计划为 JSON。
![f46bc39450cdb5848ad29d9168854d9e](https://cdn.jsdelivr.net/gh/AllenYGY/ImageSpace@main/uPic/f46bc39450cdb5848ad29d9168854d9e.png)

## 6) 记忆（Memory）

聊天顶部 `Memory` 开关可启用/关闭记忆增强。
![d9a4a026db5b4d981d25a54c96e2b5fb](https://cdn.jsdelivr.net/gh/AllenYGY/ImageSpace@main/uPic/d9a4a026db5b4d981d25a54c96e2b5fb.png)
可在消息气泡右侧点击保存到记忆。
![fc63a9dda686525425c932205b058520](https://cdn.jsdelivr.net/gh/AllenYGY/ImageSpace@main/uPic/fc63a9dda686525425c932205b058520.png)

## 7) 常见问题

**无法正常回复，对话**

- 检查.env是否配置

**Web search 调用失败**

- 检查 `PERPLEXITY_API_KEY` 是否有效。
- 若网络受限，设置 `HTTPS_PROXY` 后重试。

**计划创建后任务未显示**

- 等待异步创建完成（界面提示仍显示则说明尚未完成）。
- 任务图会自动刷新；必要时可手动刷新计划页。

---

## 8) 反馈

- 导出对话
- 导出计划

欢迎通过 GitHub Issues 提交反馈与建议！
