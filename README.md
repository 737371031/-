# 模型服务目录工具

## 工具逻辑

这是一个模型服务目录与订阅自助撤销页面工具，包含公开目录页、管理员维护页、订阅管理页以及本地 Python 服务端。

- `index.html`：模型服务目录展示页面。
- `admin.html`：模型目录后台管理页面。
- `subscriptions.html`：订阅自助撤销页面。
- `server.py`：本地 HTTP 服务与接口逻辑，负责读取/保存模型目录、管理员登录、订阅自助接口代理与审计记录。
- `api.php`：PHP 环境下的模型目录管理接口兼容实现。
- `models.json`：模型目录数据。
- `start.bat`：Windows 本地启动脚本。

## 运行方式

在 Windows 环境中双击或执行：

```bat
start.bat
```

默认访问地址：

- 首页：`http://127.0.0.1:8080/`
- 管理页：`http://127.0.0.1:8080/admin.html`
- 订阅页：`http://127.0.0.1:8080/subscriptions.html`

订阅自助功能需要通过环境变量配置 Sub2API 服务地址和管理员密钥：

```bat
set SUB2API_BASE_URL=https://your-sub2api.example.com
set SUB2API_ADMIN_KEY=your-admin-key
```

## 代码结构

当前工具按页面、接口和数据文件分离：

- 页面组件：`index.html`、`admin.html`、`subscriptions.html`
- 服务接口：`server.py`、`api.php`
- 数据配置：`models.json`
- 启动脚本：`start.bat`

运行后生成的管理员配置、订阅自助配置、日志、锁文件、临时文件和缓存不会提交到仓库。

## 更新记录

### 2026-06-19

- 初始化 Git 上传准备。
- 新增 `.gitignore`，排除运行时密钥配置、日志、临时文件和 Python 缓存。
- 新增 README，记录工具逻辑、代码结构、运行方式和更新记录。
