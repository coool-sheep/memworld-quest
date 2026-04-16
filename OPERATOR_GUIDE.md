# 数采员手册

不会代码也没关系，照着做就行。

## 1. 开始前

先把 Quest 连到电脑。

打开终端，输入：

```bash
cd /home/thj/github/hand_tracking_with_video_streamer
source /home/thj/github/hand_tracking_with_video_streamer/.venv/bin/activate
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8765 tcp:8765
```

如果 Quest 弹出“是否允许 / USB 调试 / 开发者模式”之类的提示，点“允许”。

## 2. Quest 里怎么选

打开采集 app，设置成：

- `TCP Wired`
- IP：`127.0.0.1`
- Port：`8000`
- 打开 `Camera Output`

## 3. 普通录制

比如这次数据名字叫 `1`，在电脑里输入：

```bash
python ./scripts/record_quest_dataset.py --name 1 --output-root ./data --fps 30
```

会弹出预览窗口。

录完以后：

- 点一下预览窗口
- 按 `q`

数据会在：

```text
./data/1/
```

## 4. 分段录制

如果一整段里有很多小阶段，就用这个：

```bash
python ./scripts/record_quest_dataset.py --name 1 --output-root ./data --fps 30 --enable-segmentation
```

录制时记住：

- `n`：下一段
- `q`：结束

比如你录 `A -> B -> C -> D`：

- 开始录 A
- 到 B 的时候按一次 `n`
- 到 C 的时候按一次 `n`
- 到 D 的时候按一次 `n`
- 全部结束按 `q`

## 5. 导出第一段和后面几段的组合

如果刚才做了分段录制，输入：

```bash
python ./scripts/export_stage_combinations.py --name 1 --output-root ./data
```

结果在：

```text
./data/1/exports/
```

里面会有：

- `seg1_seg2`
- `seg1_seg3`
- `seg1_seg4`

## 6. 生成检查图

如果想快速看每一段拍得怎么样，输入：

```bash
python ./scripts/generate_segment_contact_sheets.py --name 1 --output-root ./data
```

结果在：

```text
./data/1/inspection/
```

主要看里面的 `png` 图片。

## 7. 回看录制结果

输入：

```bash
python ./scripts/reproject_quest_dataset.py --name 1 --output-root ./data --fps 30
```

## 8. 最常见的问题

### `adb reverse` 报错

检查：

- Quest 有没有连上
- Quest 里有没有点“允许”
- 数据线有没有松

### 按 `q` 没反应

先点一下预览窗口，再按 `q`。

### 按 `n` 没反应

先点一下预览窗口，再按 `n`。

### 没有画面

检查 Quest 里是不是：

- 选了 `TCP Wired`
- IP 是 `127.0.0.1`
- Port 是 `8000`
- `Camera Output` 已打开
