# Windows 环境安装说明（winget 版）

适用：一台全新的 Windows 电脑，没有 Python。  
目标：安装 `memworld-quest` 运行所需的 Python、uv、Git、ADB 环境。  
不包含 APK 安装。

## 1. 安装基础工具

用 **PowerShell** 执行：

```powershell
winget install -e --id Python.Python.3.13
winget install -e --id Git.Git
winget install -e --id Google.PlatformTools
```

装完后，关闭 PowerShell，重新打开。

## 2. 检查安装

```powershell
py -3.13 --version
git --version
adb version
```

能显示版本号即可。

## 3. 下载仓库

```powershell
cd "$env:USERPROFILE\Desktop"
git clone https://github.com/coool-sheep/memworld-quest.git
cd memworld-quest
```

## 4. 安装 uv

```powershell
py -3.13 -m pip install -U uv -i https://pypi.tuna.tsinghua.edu.cn/simple
```

检查：

```powershell
py -3.13 -m uv --version
```

## 5. 安装项目依赖

```powershell
py -3.13 -m uv sync --python 3.13 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

验证：

```powershell
py -3.13 -m uv run python -c "import numpy, pyarrow, PIL, imageio, websockets; print('env ok')"
```

看到：

```text
env ok
```

说明 Python 环境正常。

## 6. 检查 Quest 连接

先用 USB 线连接 Quest，然后执行：

```powershell
adb devices
```

如果 Quest 里弹出 USB 调试授权，选择允许。

正常结果类似：

```text
List of devices attached
XXXXXXXX    device
```

如果显示 `unauthorized`，说明 Quest 里还没授权。

## 7. 建立端口映射

```powershell
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8765 tcp:8765
```

## 8. 启动录制

```powershell
py -3.13 -m uv run python ./scripts/record_quest_dataset.py --name test_record --output-root ./data --fps 30
```

需要分段录制时：

```powershell
py -3.13 -m uv run python ./scripts/record_quest_dataset.py --name test_record --output-root ./data --fps 30 --enable-segmentation
```

## 常见判断标准

环境是否成功，只看两个结果：

```text
env ok
```

以及：

```text
adb devices 能看到 device
```

这两个都正常，Windows 端环境基本就好了。
