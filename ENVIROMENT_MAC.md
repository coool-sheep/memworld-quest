
```md
# Mac 安装项目环境

适用情况：

- 已经拿到了 `memworld-quest` 文件夹；
- 电脑不能访问 GitHub；
- 但可以正常访问网页或国内 Python 镜像；
- 使用者不需要懂 Python，也不需要懂终端。

---

# 1. 打开终端

按下面步骤打开终端：

1. 按 `Command + 空格`
2. 输入 `终端`
3. 回车

---

# 2. 先确认有没有 Homebrew

在终端里复制下面命令，然后回车：

```bash
brew --version
```

如果能看到版本号，例如：

```text
Homebrew 4.x.x
```

说明有 Homebrew，继续看「方式一」。

如果提示：

```text
command not found: brew
```

说明没有 Homebrew，跳到「方式二」。

---

# 方式一：电脑上有 Homebrew

## 1. 安装工具

```bash
brew install uv
```

## 2. 进入项目文件夹

如果项目文件夹在「下载」目录，执行：

```bash
cd ~/Downloads/memworld-quest
```

如果不在下载目录，需要把路径换成实际位置。

例如在桌面：

```bash
cd ~/Desktop/memworld-quest
```

## 3. 安装项目环境

```bash
uv sync --python 3.13 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

## 4. 验证是否成功

```bash
uv run python --version
```

再执行：

```bash
uv run python -c "import numpy, pyarrow, PIL, imageio; print('env ok')"
```

如果看到：

```text
env ok
```

说明环境安装成功。

---

# 方式二：电脑上没有 Homebrew

## 1. 安装 Python 3.13

用浏览器打开：

```text
https://www.python.org/downloads/macos/
```

下载 Python 3.13 的 macOS 安装包。

文件一般类似：

```text
python-3.13.x-macos11.pkg
```

下载后双击安装，一直点继续即可。

安装完成后，在终端执行：

```bash
python3.13 --version
```

如果看到类似：

```text
Python 3.13.x
```

说明 Python 安装成功。

---

## 2. 安装 uv

在终端执行：

```bash
python3.13 -m pip install -U uv -i https://pypi.tuna.tsinghua.edu.cn/simple
```

验证 uv 是否安装成功：

```bash
python3.13 -m uv --version
```

如果能看到版本号，说明 uv 安装成功。

---

## 3. 进入项目文件夹

如果项目文件夹在「下载」目录，执行：

```bash
cd ~/Downloads/memworld-quest
```

如果项目文件夹在桌面，执行：

```bash
cd ~/Desktop/memworld-quest
```

如果不知道路径，可以把项目文件夹直接拖进终端窗口，终端会自动填入路径。

---

## 4. 安装项目环境

确认已经进入 `memworld-quest` 文件夹后，执行：

```bash
python3.13 -m uv sync --python 3.13 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

这一步可能需要几分钟。

---

## 5. 验证是否成功

```bash
python3.13 -m uv run python --version
```

再执行：

```bash
python3.13 -m uv run python -c "import numpy, pyarrow, PIL, imageio; print('env ok')"
```

如果看到：

```text
env ok
```

说明环境安装成功。

---

# 常见问题

## 1. command not found: brew

说明电脑没有 Homebrew。

直接使用「方式二」。

---

## 2. command not found: python3.13

说明 Python 3.13 没装好。

重新下载安装 Python 3.13：

```text
https://www.python.org/downloads/macos/
```

---

## 3. 安装很慢

可以先等一会儿。

如果长时间不动，可以重新执行安装命令。

有 Homebrew 的情况：

```bash
uv sync --python 3.13 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

没有 Homebrew 的情况：

```bash
python3.13 -m uv sync --python 3.13 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

---

# 最短流程

如果没有 Homebrew，只需要做这几步：

1. 安装 Python 3.13；
2. 打开终端；
3. 进入 `memworld-quest` 文件夹；
4. 执行下面三条命令：

```bash
python3.13 -m pip install -U uv -i https://pypi.tuna.tsinghua.edu.cn/simple
python3.13 -m uv sync --python 3.13 --index-url https://pypi.tuna.tsinghua.edu.cn/simple
python3.13 -m uv run python -c "import numpy, pyarrow, PIL, imageio; print('env ok')"
```

如果看到：

```text
env ok
```

说明环境安装完成。
```