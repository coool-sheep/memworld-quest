
````md id="q1w2e3"
# Windows 安装项目环境

适用情况：

- 已经拿到了 `memworld-quest` 文件夹；
- 电脑不能访问 GitHub；
- 但可以正常访问网页或国内 Python 镜像；
- 使用者不需要懂 Python，也不需要懂命令行。

---

# 1. 准备项目文件夹

如果拿到的是压缩包，比如：

```text
memworld-quest.zip
````

先右键解压。

解压后应该得到一个文件夹，名字可能是：

```text
memworld-quest
```

或者：

```text
memworld-quest-main
```

都可以。

建议把它放到桌面，方便后面操作。

---

# 2. 安装 Python 3.13

用浏览器打开：

```text
https://www.python.org/downloads/windows/
```

下载 Python 3.13 的 Windows 安装包。

文件一般类似：

```text
python-3.13.x-amd64.exe
```

双击安装。

注意：安装界面最下面有一个选项：

```text
Add python.exe to PATH
```

建议勾选。

然后点击：

```text
Install Now
```

一直等安装完成。

---

# 3. 打开 PowerShell

按下面步骤打开：

1. 按 `Win` 键；
2. 输入 `PowerShell`；
3. 回车打开。

不需要管理员权限。

---

# 4. 检查 Python 是否安装成功

在 PowerShell 里输入：

```powershell
py -3.13 --version
```

如果看到类似：

```text
Python 3.13.x
```

说明 Python 安装成功。

如果这一步失败，说明 Python 没装好，重新安装 Python 3.13。

---

# 5. 安装 uv

继续在 PowerShell 里执行：

```powershell
py -3.13 -m pip install -U uv -i https://pypi.tuna.tsinghua.edu.cn/simple
```

验证 uv 是否安装成功：

```powershell
py -3.13 -m uv --version
```

如果能看到版本号，说明 uv 安装成功。

---

# 6. 进入项目文件夹

假设项目文件夹在桌面，名字叫：

```text
memworld-quest
```

执行：

```powershell
cd "$env:USERPROFILE\Desktop\memworld-quest"
```

如果你的文件夹叫：

```text
memworld-quest-main
```

就执行：

```powershell
cd "$env:USERPROFILE\Desktop\memworld-quest-main"
```

如果不知道路径，可以这样做：

1. 在 PowerShell 里先输入 `cd `，注意后面有一个空格；
2. 把项目文件夹直接拖进 PowerShell 窗口；
3. 回车。

---

# 7. 安装项目环境

确认已经进入项目文件夹后，执行：

```powershell
py -3.13 -m uv sync --python 3.13 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

这一步可能需要几分钟。

如果中间没有明显报错，等待它结束即可。

---

# 8. 验证是否安装成功

执行：

```powershell
py -3.13 -m uv run python --version
```

再执行：

```powershell
py -3.13 -m uv run python -c "import numpy, pyarrow, PIL, imageio; print('env ok')"
```

如果看到：

```text
env ok
```

说明环境安装成功。

---

# 常见问题

## 1. py 不是内部或外部命令

说明 Python 没有装好。

重新安装 Python 3.13，并且安装时勾选：

```text
Add python.exe to PATH
```

---

## 2. 找不到项目文件夹

建议把项目文件夹放到桌面。

然后执行：

```powershell
cd "$env:USERPROFILE\Desktop\memworld-quest"
```

如果文件夹名字不一样，把最后的 `memworld-quest` 改成实际名字。

---

## 3. 安装很慢

可以先等一会儿。

如果长时间不动，可以重新执行：

```powershell
py -3.13 -m uv sync --python 3.13 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 4. 提示 No such file or directory

通常是因为没有进入项目文件夹。

先执行：

```powershell
pwd
```

看当前路径是不是项目文件夹。

正确情况下，路径最后应该类似：

```text
memworld-quest
```

或者：

```text
memworld-quest-main
```

---

# 最短流程

如果已经安装好了 Python 3.13，只需要：

1. 打开 PowerShell；
2. 进入项目文件夹；
3. 执行下面三条命令：

```powershell
py -3.13 -m pip install -U uv -i https://pypi.tuna.tsinghua.edu.cn/simple

py -3.13 -m uv sync --python 3.13 --index-url https://pypi.tuna.tsinghua.edu.cn/simple

py -3.13 -m uv run python -c "import numpy, pyarrow, PIL, imageio; print('env ok')"
```

如果看到：

```text
env ok
```

说明环境安装完成。

```
```
