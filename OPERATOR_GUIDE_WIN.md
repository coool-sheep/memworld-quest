# memworld-quest Windows 傻瓜版操作教程

适用对象：Windows 电脑上的 operator / 数采员。  
前提：Quest 里的采集 App 已经安装好。  
仓库来源：项目压缩包通过 U 盘传到电脑，不需要 Git。  
本文只讲 Windows 环境、ADB、uv、录制流程。

---

## 1. 第一次安装环境

只需要做一次。

### 1.1 打开 PowerShell

按 `Win` 键，搜索：

```text
PowerShell
```

打开：

```text
Windows PowerShell
```

后面的命令都在 PowerShell 里执行。

---

### 1.2 安装 ADB

执行：

```powershell
winget install -e --id Google.PlatformTools
```

装完后，关闭 PowerShell，重新打开。

检查 ADB：

```powershell
adb version
```

如果能显示版本号，说明 ADB 安装成功。

---

### 1.3 安装 uv

执行：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

装完后，关闭 PowerShell，重新打开。

检查 uv：

```powershell
uv --version
```

如果能显示版本号，说明 uv 安装成功。

如果提示找不到 `uv`，执行：

```powershell
$env:Path = "$HOME\.local\bin;" + $env:Path
uv --version
```

如果这样能显示版本号，说明只是当前 PowerShell 没刷新。之后重新打开 PowerShell 通常就正常了。

---

## 2. 解压项目文件夹

把 U 盘里的项目压缩包复制到电脑。

建议放到：

```text
C:\memworld-quest.zip
```

右键压缩包，选择：

```text
全部解压
```

建议解压后的目录是：

```text
C:\memworld-quest
```

最终进入的文件夹里应该能看到：

```text
README.md
pyproject.toml
scripts
```

如果解压后是这种结构：

```text
C:\memworld-quest\memworld-quest\README.md
```

说明里面多套了一层。后面要进入里面那一层。

---

## 3. 进入项目目录

打开 PowerShell。

如果项目目录是：

```text
C:\memworld-quest
```

执行：

```powershell
cd C:\memworld-quest
```

检查当前目录内容：

```powershell
dir
```

确认能看到：

```text
README.md
pyproject.toml
scripts
```

如果看不到，说明目录进错了，需要进入真正包含 `pyproject.toml` 的那一层。

---

## 4. 安装项目依赖

在项目目录里执行：

```powershell
uv sync --python 3.13 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

如果提示没有 Python 3.13，执行：

```powershell
uv python install 3.13
uv sync --python 3.13 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

验证环境：

```powershell
uv run python -c "import numpy, pyarrow, PIL, imageio, websockets; print('env ok')"
```

看到：

```text
env ok
```

说明 Python 环境安装成功。

---

## 5. 每次录制前的准备

每次重新插 Quest、重启电脑、重新打开 App 后，都建议重新做这一节。


### 5.0 前置步骤（配置网络）
在Quest上打开Hand Tracking应用：
1. 长按，点击`查看详情`
2. 点击启动

如果打不开一般是网络问题：在电脑端打开UU加速器如下图（需要有会员），
![image](image.png).
点击一键加速，按照里面指示配置无线网络：
1. 在wifi选择界面里点右边箭头，在连接前点`高级`
2. 在`IP设置`处，选择为`静态IP`；
3. IP地址和网关地址按照指示输入
4. 前缀长度为16.
5. 点击保存，然后回到wifi界面，输入密码点连接。
6. 重新打开quest应用


### 5.1 连接 Quest

用 USB-C 数据线连接 Quest 和电脑。

注意：

- 必须使用能传数据的线；
- Quest 必须开机；
- Quest 需要开启开发者模式；
- 如果 Quest 里弹出 USB 调试授权，选择允许；
- 如果有“始终允许这台电脑”，建议勾选。

---

### 5.2 检查 Quest 是否连接成功

执行：

```powershell
adb devices
```

正常结果类似：

```text
List of devices attached
XXXXXXXX    device
```

只要最后是：

```text
device
```

就说明连接成功。

如果显示：

```text
unauthorized
```

说明 Quest 里还没有点允许。戴上 Quest，找到 USB 调试弹窗，点允许，然后重新执行：

```powershell
adb devices
```

如果没有任何设备，执行：

```powershell
adb kill-server
adb start-server
adb devices
```

如果还是没有设备，检查：

- USB 线是否能传数据；
- Quest 是否开机；
- Quest 是否开启开发者模式；
- 是否没有点 USB 调试允许；
- 换一个 USB 口；
- 换一根数据线。

---

### 5.3 建立端口映射

执行：

```powershell
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8765 tcp:8765
```

检查映射是否成功：

```powershell
adb reverse --list
```

正常能看到：

```text
tcp:8000 tcp:8000
tcp:8765 tcp:8765
```

如果想重新设置端口映射，执行：

```powershell
adb reverse --remove-all
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8765 tcp:8765
```

---

## 6. Quest App 设置

打开 Quest 里的采集 App。

连接方式选择：

```text
TCP Wired
```

IP 填：

```text
127.0.0.1
```

端口填：

```text
8000
```

打开这些选项：

```text
Camera Output
Head Pose
Show Landmarks
```

如果界面里写的是：

```text
Camera Uplink
```

或者类似相机上传的选项，也需要打开。

---

## 7. 普通录制

假设这次数据名叫：

```text
test01
```

在 PowerShell 里确认当前位于项目目录：

```powershell
cd C:\memworld-quest
```

开始录制：

```powershell
uv run python ./scripts/record_quest_dataset.py --name test01 --output-root ./data --fps 30
```

录制开始后，电脑会弹出预览窗口。

结束录制：

1. 用鼠标点一下预览窗口；
2. 按键盘 `q`。

不要直接关闭 PowerShell 窗口。

---

## 8. 分段录制

如果一个任务需要分成多个阶段，就用分段录制。

例如：

```text
seg1：初始状态
seg2：拿起物体
seg3：移动物体
seg4：放下物体
```

开始分段录制：

```powershell
uv run python ./scripts/record_quest_dataset.py --name test_segments --output-root ./data --fps 30 --enable-segmentation
```

录制过程中：

```text
n：进入下一段
q：结束录制
```

注意：需要先用鼠标点一下预览窗口，再按 `n` 或 `q`。

---

## 9. 导出分段组合

如果做了分段录制，可以导出 `seg1 + segN` 的组合数据。

例如刚才的数据名是：

```text
test_segments
```

执行：

```powershell
uv run python ./scripts/export_stage_combinations.py --name test_segments --output-root ./data
```

输出位置：

```text
data\test_segments\exports
```

常见结果：

```text
seg1_seg2
seg1_seg3
seg1_seg4
```

---

## 10. 生成分段检查图

用于快速检查每一段有没有录对。

执行：

```powershell
uv run python ./scripts/generate_segment_contact_sheets.py --name test_segments --output-root ./data
```

输出位置：

```text
data\test_segments\inspection
```

打开里面的图片，检查：

- 画面是否正常；
- 有没有黑屏；
- 有没有明显卡顿；
- 分段是否按对；
- 每段动作是否符合任务要求。

---

## 11. 回看录制结果

普通数据回看：

```powershell
uv run python ./scripts/reproject_quest_dataset.py --name test01 --output-root ./data --fps 30
```

分段数据回看：

```powershell
uv run python ./scripts/reproject_quest_dataset.py --name test_segments --output-root ./data --fps 30
```

---

## 12. 数据保存位置

如果录制名是：

```text
test01
```

数据会保存在：

```text
data\test01
```

常见文件：

```text
camera.mp4
camera_frames.parquet
aligned_frames.parquet
telemetry_raw.parquet
session.json
```

分段录制还会有：

```text
segments.json
```

导出的组合数据会在：

```text
data\test_segments\exports
```

检查图会在：

```text
data\test_segments\inspection
```

---

## 13. 每天录制最短流程

每天正式录制时，按这个流程走。

### 13.1 打开 PowerShell，进入项目目录

```powershell
cd C:\memworld-quest
```

如果项目不在这个位置，就改成实际路径。

### 13.2 检查 Quest

```powershell
adb devices
```

必须看到：

```text
device
```

### 13.3 建立端口映射

```powershell
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8765 tcp:8765
```

### 13.4 打开 Quest App

设置：

```text
TCP Wired
IP = 127.0.0.1
Port = 8000
Camera Output = ON
Head Pose = ON
```

### 13.5 开始录制

普通录制：

```powershell
uv run python ./scripts/record_quest_dataset.py --name test01 --output-root ./data --fps 30
```

分段录制：

```powershell
uv run python ./scripts/record_quest_dataset.py --name test_segments --output-root ./data --fps 30 --enable-segmentation
```

### 13.6 结束录制

普通录制：

```text
点一下预览窗口，然后按 q
```

分段录制：

```text
n：下一段
q：结束
```

---

## 14. 数据命名规则

建议只用：

```text
英文
数字
下划线
```

推荐：

```text
20260512_test01
pick_cup_01
operatorA_test01
```

不要用：

```text
第一次测试
test 01
拿杯子#1
```

---

## 15. 常见问题

### 15.1 `uv` 不是内部或外部命令

执行：

```powershell
$env:Path = "$HOME\.local\bin;" + $env:Path
uv --version
```

如果还不行，重新安装 uv：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

然后关闭 PowerShell，重新打开。

---

### 15.2 `adb` 不是内部或外部命令

重新安装 ADB：

```powershell
winget install -e --id Google.PlatformTools
```

然后关闭 PowerShell，重新打开。

检查：

```powershell
adb version
```

---

### 15.3 `adb devices` 没有设备

执行：

```powershell
adb kill-server
adb start-server
adb devices
```

如果还是没有，检查：

- Quest 是否开机；
- USB 线是否能传数据；
- 是否点了 USB 调试允许；
- Quest 是否开启开发者模式；
- 是否需要换 USB 口或换线。

---

### 15.4 `adb devices` 显示 `unauthorized`

戴上 Quest，点允许 USB 调试。

然后重新执行：

```powershell
adb devices
```

---

### 15.5 没有画面

先检查端口映射：

```powershell
adb reverse --list
```

必须看到：

```text
tcp:8000 tcp:8000
tcp:8765 tcp:8765
```

再检查 Quest App：

```text
TCP Wired
IP = 127.0.0.1
Port = 8000
Camera Output = ON
Head Pose = ON
```

然后重新启动录制命令。

---

### 15.6 按 `q` 没反应

先用鼠标点一下预览窗口，再按：

```text
q
```

---

### 15.7 按 `n` 没反应

只有分段录制模式才支持 `n`。

必须用这个命令启动：

```powershell
uv run python ./scripts/record_quest_dataset.py --name test_segments --output-root ./data --fps 30 --enable-segmentation
```

然后点一下预览窗口，再按：

```text
n
```

---

## 16. 成功标准

全部跑通时，应满足下面四点。

### 16.1 环境正常

```powershell
uv run python -c "import numpy, pyarrow, PIL, imageio, websockets; print('env ok')"
```

输出：

```text
env ok
```

### 16.2 Quest 正常

```powershell
adb devices
```

能看到：

```text
device
```

### 16.3 端口正常

```powershell
adb reverse --list
```

能看到：

```text
tcp:8000 tcp:8000
tcp:8765 tcp:8765
```

### 16.4 数据正常

录制结束后能找到：

```text
data\你的数据名\camera.mp4
data\你的数据名\session.json
data\你的数据名\aligned_frames.parquet
```

看到这些文件，就说明录制流程跑通。