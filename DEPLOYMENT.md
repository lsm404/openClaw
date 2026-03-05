## OpenClaw 部署与打包说明

### 一、客户端（Windows）打包为 `.exe`

> 注意：必须在 **Windows 环境** 中操作（真实 Windows / 虚拟机均可）。  
> 下面示例假设项目目录为 `C:\openclaw-auto`。

#### 1. 准备环境

1. 安装 **Python 3.10+**
   - 从 Python 官网下载安装，安装时勾选 **“Add Python to PATH”**。
2. 打开命令行：

```bash
cd C:\openclaw-auto

python -m venv .venv
.\.venv\Scripts\activate

pip install -U pip
pip install -r requirements.txt
```

#### 2. 创建启动脚本（仅首次需要）

在项目根目录新建 `run_desktop.py`：

```python
from openclaw.desktop_app import main

if __name__ == "__main__":
    main()
```

#### 3. 使用 PyInstaller 打包

```bash
pip install pyinstaller

pyinstaller --noconfirm --windowed --name OpenClaw run_desktop.py
```

生成结果：

- 可执行程序目录：`dist\OpenClaw\`
- 主程序：`dist\OpenClaw\OpenClaw.exe`

> 可选：如需「单文件」：
>
> ```bash
> pyinstaller --noconfirm --windowed --onefile --name OpenClaw run_desktop.py
> ```
> 生成：`dist\OpenClaw.exe`

#### 4. 分发和运行

- 把 `dist\OpenClaw\` 整个文件夹压缩成 zip 发给用户，解压后双击 `OpenClaw.exe` 即可。
- 客户端内置的后端默认地址为：
  - `http://49.235.172.63:8000/`
  - 如需修改，可在运行环境中设置 `BACKEND_BASE_URL` 环境变量覆盖。

---

### 二、服务端（宝塔 Linux 服务器）部署 FastAPI 后端

> 假设：  
> - 服务器系统为 Linux（CentOS / Ubuntu 均可），已安装宝塔。  
> - 项目部署在 `/opt/openclaw-auto`。  
> - 后端监听端口 `8000`。

#### 1. 安装基础环境

在宝塔终端或 SSH 中执行（根据系统选择对应命令）：

```bash
# CentOS / Rocky / AlmaLinux
yum update -y
yum install -y python3 python3-pip git

# Ubuntu / Debian
apt update -y
apt install -y python3 python3-pip git
```

#### 2. 获取代码

```bash
cd /opt
git clone https://github.com/<你的GitHub用户名>/<仓库名>.git openclaw-auto
cd openclaw-auto
```

（如果是本地上传的压缩包，解压到 `/opt/openclaw-auto` 即可。）

#### 3. 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install -r requirements.txt
```

#### 4. 启动后端（前台验证）

```bash
cd /opt/openclaw-auto
source .venv/bin/activate

uvicorn wechat_backend.app:app --host 0.0.0.0 --port 8000
```

浏览器访问：

- `http://服务器公网IP:8000/health`
- 返回 `{"status":"ok"}` 表示后端正常。

#### 5. 后台常驻运行（简易方案）

```bash
cd /opt/openclaw-auto
source .venv/bin/activate

nohup uvicorn wechat_backend.app:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
```

查看进程（可选）：

```bash
ps aux | grep uvicorn
```

> 正式环境可以用宝塔「守护进程」或 `systemd` 配置为开机自启，这里给的是最小可用流程。

#### 6. 开放端口 / 安全组

在云厂商控制台的「安全组」开放 **TCP 8000**。  
如使用 firewalld（CentOS）：

```bash
firewall-cmd --add-port=8000/tcp --permanent
firewall-cmd --reload
```

#### 7. 微信公众号 IP 白名单

在微信公众平台：

- 打开：**开发 → 基本配置 / 开发设置 → 服务器 IP 白名单**。
- 添加这台服务器的公网 IP，保存。

#### 8. 客户端配置

- 客户端当前默认后端地址为：`http://49.235.172.63:8000/`。  
- 如需指向其他服务器：
  - 启动前设置环境变量 `BACKEND_BASE_URL`，例如：

```bash
BACKEND_BASE_URL=http://你的服务器IP:8000
```

或在以后增加的设置界面中调整。

