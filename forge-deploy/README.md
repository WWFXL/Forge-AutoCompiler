# Forge CLI 使用文档

## 功能

通过终端命令快速创建新会话并打开浏览器。

## 安装

### 方法 1：添加 alias（推荐）

```bash
echo "alias forge='/workspace/forge-deploy/forge'" >> ~/.bashrc
source ~/.bashrc
```

### 方法 2：加入 PATH

```bash
echo 'export PATH="/workspace/forge-deploy:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## 使用

### 基本用法

```bash
forge compile
```

执行后：
1. 自动创建新 thread
2. 打开浏览器跳转到会话页面
3. 在页面输入编译请求，点击发送

### 指定网关地址

```bash
forge compile http://localhost:51115
```

## 前提条件

- DeerFlow 服务运行在 51115 端口
- 浏览器可访问 localhost

## 原理

1. 调用 `POST /api/threads` 创建新 thread
2. 获取 thread_id
3. 打开浏览器到 `/workspace/chats/{thread_id}`
