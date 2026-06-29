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

- 首页：`http://127.0.0.1:18080/`
- 管理页：`http://127.0.0.1:18080/admin.html`
- 订阅页：`http://127.0.0.1:18080/subscriptions.html`

订阅自助功能需要通过环境变量配置 Sub2API 服务地址和管理员密钥：

```bat
set SUB2API_BASE_URL=https://your-sub2api.example.com
set SUB2API_ADMIN_KEY=your-admin-key
```

## Linux 服务器独立目录部署

推荐把本工具部署在独立目录中，不要混放到已有项目目录里。下面示例使用：

- 项目目录：`/opt/model-catalog`
- 本地监听端口：`18080`
- 对外访问路径：`https://你的域名/ai-catalog/`
- 反向代理：Nginx
- 运行方式：systemd 常驻服务

### 1. 准备独立目录

```bash
sudo mkdir -p /opt/model-catalog
sudo chown -R "$USER:$USER" /opt/model-catalog
cd /opt/model-catalog
git clone https://github.com/737371031/-.git .
```

如果服务器不能直接拉 GitHub，也可以把仓库文件上传到 `/opt/model-catalog`，但不要上传本地运行生成的配置、日志、缓存文件。

### 2. 检查运行环境

```bash
python3 --version
cd /opt/model-catalog
python3 -m py_compile server.py
python3 -m json.tool models.json >/dev/null
```

如果服务器没有 Python 3，先安装：

```bash
sudo apt update
sudo apt install -y python3 git nginx
```

CentOS / Rocky Linux 可使用：

```bash
sudo dnf install -y python3 git nginx
```

### 3. 配置运行时环境变量

不要把真实密钥写进 README 或提交到 Git。建议把密钥放在 `/etc/model-catalog.env`：

```bash
sudo install -m 600 -o root -g root /dev/null /etc/model-catalog.env
sudo nano /etc/model-catalog.env
```

写入以下内容，并替换成你自己的 Sub2API 地址和管理员密钥：

```env
SUB2API_BASE_URL=https://your-sub2api.example.com
SUB2API_ADMIN_KEY=your-admin-key
SUB2API_API_PREFIX=/api/v1
SUB2API_AUTH_ME_PATH=/auth/me
SELF_SERVICE_API_PATH=/self-api
SELF_SERVICE_COOKIE_PATH=/ai-catalog
```

如果你用独立二级域名部署在根路径，例如 `https://catalog.example.com/`，把 `SELF_SERVICE_COOKIE_PATH` 改成 `/`。

### 4. 创建 systemd 服务

创建独立运行用户：

```bash
sudo useradd --system --home /opt/model-catalog --shell /usr/sbin/nologin model-catalog || true
sudo chown -R model-catalog:model-catalog /opt/model-catalog
```

创建服务文件：

```bash
sudo nano /etc/systemd/system/model-catalog.service
```

写入：

```ini
[Unit]
Description=Model Catalog Tool
After=network.target

[Service]
Type=simple
User=model-catalog
Group=model-catalog
WorkingDirectory=/opt/model-catalog
EnvironmentFile=/etc/model-catalog.env
ExecStart=/usr/bin/python3 /opt/model-catalog/server.py --host 127.0.0.1 --port 18080
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/opt/model-catalog

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now model-catalog
sudo systemctl status model-catalog
```

本机检查：

```bash
curl -I http://127.0.0.1:18080/
curl http://127.0.0.1:18080/api.php?action=status
```

### 5. 配置 Nginx 子路径反向代理

在已有站点的 `server { ... }` 中加入下面配置。注意 `proxy_pass` 末尾必须带 `/`，这样 `/ai-catalog/` 前缀会被去掉，工具内部的 `api.php`、`models.json` 相对路径才能正常工作。

```nginx
location = /ai-catalog {
    return 301 /ai-catalog/;
}

location /ai-catalog/ {
    proxy_pass http://127.0.0.1:18080/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;
}
```

检查并重载 Nginx：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

访问：

- 首页：`https://你的域名/ai-catalog/`
- 管理页：`https://你的域名/ai-catalog/admin.html`
- 订阅页：`https://你的域名/ai-catalog/subscriptions.html`

第一次进入管理页后，会提示设置管理员密码。密码配置会生成在 `/opt/model-catalog/model-admin-config.json`，不要提交或公开这个文件。

### 6. 首次初始化安全

生产环境第一次访问 `/admin.html` 时会创建管理员密码。如果服务器已经对公网开放，建议先临时限制后台入口，避免别人抢先初始化：

```nginx
location = /ai-catalog/admin.html {
    allow 你的公网IP;
    deny all;
    proxy_pass http://127.0.0.1:18080/admin.html;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

完成管理员密码设置后，可以继续保留 IP 白名单，也可以改成只允许内网或 VPN 访问。

本工具建议只通过 HTTPS 访问。自助订阅会话 Cookie 带有 `Secure` 标记，HTTP 环境下可能无法正常发送。

### 7. 配置订阅自助入口

如果 Sub2API 支持配置跳转链接，推荐让它跳转到：

```text
https://你的域名/ai-catalog/subscriptions.html?user_id={用户ID}&token={登录凭证}&endpoint=/ai-catalog/self-api
```

其中 `endpoint=/ai-catalog/self-api` 是浏览器访问的外部路径，Nginx 会转发到 Python 服务内部的 `/self-api`。

### 8. Python 与 PHP 部署模式

需要订阅自助撤销功能时，推荐使用上面的 Python `server.py` 部署方式。Python 服务会接管 `api.php` 路径，并提供模型目录管理、自助订阅接口代理和审计日志。

`api.php` 只适合 PHP-FPM 环境下的模型目录管理兼容部署，不包含 Sub2API 自助撤销代理逻辑。不要在同一个访问路径下同时让 Nginx 把 `api.php` 交给 PHP-FPM，又把其他路径反代给 Python，否则登录态、配置文件和接口行为会不一致。

### 9. 备份与运行时文件

需要备份的运行时文件：

- `/opt/model-catalog/models.json`：模型目录数据。
- `/opt/model-catalog/model-admin-config.json`：管理员密码哈希和会话密钥。
- `/opt/model-catalog/subscription-self-config.json`：订阅自助会话密钥。
- `/opt/model-catalog/subscription-self-audit.log`：订阅自助操作审计日志。

这些文件可能包含敏感信息，备份时也要限制权限，不要放进公开仓库。

### 10. 更新部署

后续更新代码：

```bash
cd /opt/model-catalog
sudo -u model-catalog git pull
python3 -m py_compile server.py
python3 -m json.tool models.json >/dev/null
sudo systemctl restart model-catalog
sudo systemctl status model-catalog
```

### 11. 常见排查

- 页面能打开但保存失败：检查 `/opt/model-catalog` 是否属于 `model-catalog` 用户，确认 `models.json` 可写。
- 管理页提示接口不可用：检查 Nginx 子路径代理是否带了末尾 `/`，并确认 `systemctl status model-catalog` 正常。
- 订阅自助登录失败：检查 `/etc/model-catalog.env` 中的 `SUB2API_BASE_URL`、`SUB2API_ADMIN_KEY`、`SUB2API_API_PREFIX` 是否与 Sub2API 实际接口一致。
- 与已有项目冲突：换一个子路径，例如 `/model-list/`，同时修改 Nginx 路径、`SELF_SERVICE_COOKIE_PATH` 和订阅入口里的 `endpoint`。
- 端口冲突：把 systemd 里的 `--port 18080` 改成未占用端口，并同步修改 Nginx `proxy_pass`。
- 后台 Cookie 影响同域名其他项目：当前管理员 Cookie 路径是 `/`，同域名其他路径也会携带该 Cookie。通常不会被其他项目识别，但更稳妥的方式是后台保持 IP 白名单、VPN 或独立二级域名。

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
- 补充 Linux 服务器独立目录部署教程，包含 systemd 常驻服务、Nginx 子路径反向代理、环境变量和排查步骤。
- 补充首次初始化安全、HTTPS/Cookie、Python/PHP 部署差异和运行时文件备份说明。
- 将默认本地端口从 `8080` 调整为 `18080`，降低与已有项目或常见服务冲突的概率。
- 新增独立教程页 `guide.html`，将 `工具文件` 中的接入文档整理为可部署的图文引导网页。
- 从 `apikey添加指南.docx` 提取并本地归档了教程截图，避免继续依赖飞书临时图片链接。

### 2026-06-29

- 按 `工具文件/apikey添加指南.md` 重新收敛了 `guide.html` 的教程文案，减少主观扩写，改回更贴近原文档的步骤表述。
- 将域名使用说明明确归回 CCS 配置前置步骤，区分国内加速域名 `https://wuzuapi.xyz` 与直连域名 `https://wuzuapi.com`（需要开魔法）。
- 修正了 CCS 导入相关截图说明，改回网站 key 页面里的导入入口、弹出打开、启用即可等原始流程。
- 单独恢复了 GPT 5.5 提醒层级，并将模型修改步骤改为明确的 `gpt-5.4 -> gpt-5.4-2026-03-05` 替换说明。
- 将 GPT Image 2 和 OpenCode 教程文案同步收敛到原文档动作表达，同时保留本地化图片和点击放大预览能力。
- 将 `guide.html` 重构为严格按原文顺序的线性教程页，取消易打乱阅读顺序的拆分布局，改成从上到下连续阅读的图文结构。
- 修正了 `05-choose-cli-tool.png` 到 `10-change-model-name.png` 的 CCS 图文映射顺序，恢复为“先下载 CCS、再导入、再打开、再启用、再进入配置、最后改模型名”的原始流程。
- 重新拆分了 `GPT-IMAGE-2调用接口文档` 与 `GPT IMAGE 2 生图 wuzu api skill 使用指南` 的独立目录入口，避免两段内容混在同一个导航节点里。
- 重做了教程页视觉层级，强化售后群提示、重点提醒和步骤编号，同时补充滚动显现、目录高亮、滚动进度和图片上一张/下一张放大预览。
- 参考成熟设计系统的中性色、功能色和主色分工，重做 `guide.html` 的现代化配色，去掉旧暖棕/玫红风格，改为冷白底、蓝青主色、克制红色警告和更轻的卡片阴影。
- 修复教程目录跳转不稳定的问题：改为脚本精确计算吸顶头部偏移，补充 hash 直达校准、底部滚动缓冲，并给教程截图写入宽高以避免懒加载导致锚点偏移。
- 按 `工具文件/WUZU-IMAGE.html` 的 API 调用文档修复 GPT Image 2 生图 skill：补齐 `model_config_key`、自定义宽高、`output_width/output_height`、`aspect_ratio/resolution`、`response_format`、异步任务轮询和返回解析兼容。
- 同步修复生图 skill 的本地网页版本，新增对应高级参数入口，数量上限调整为 `1-9`，并保留旧版比例转像素开关用于兼容旧流程。
- 重新生成 `downloads/gpt-image-2-generator-share-20260520-140609.zip` 分享包，包内保留顶层目录结构，并排除输出图片、历史记录、缓存文件和真实 token。
