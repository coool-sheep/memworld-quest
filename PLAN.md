# 分段录制与组合导出实现计划

## 目标

在现有数据采集流程中增加一个可选的“分段标记”能力：

- 录制开始后自动进入第 1 段。
- 操作员在录制过程中按下“分段”键，结束当前段并开始下一段。
- 录制结束时自动关闭最后一段。
- 录制完成后，基于分段信息离线导出组合视频。
- 当前目标组合规则为：把第 1 段与后续每一段分别拼接，生成 `1+2`、`1+3`、`1+4` ... 这类结果。

## 背景与现状

当前仓库的录制主流程位于 `scripts/record_quest_dataset.py`，录制结束后会在一个数据集目录下写出：

- `camera.mp4`
- `telemetry_raw.parquet`
- `camera_frames.parquet`
- `aligned_frames.parquet`
- `session.json`

现有流程没有“阶段标记 / 分段标记”概念，但已经具备以下基础条件：

- 每个相机帧都有 `camera_frame_index`、`camera_frame_id`、`camera_timestamp_ns`
- 对齐后的 `aligned_frames.parquet` 是一帧一行，适合作为切片与导出的主索引
- 仓库已经依赖 `imageio` 和 `imageio-ffmpeg`，具备离线导出 MP4 的基础能力

因此，最小侵入方案应为：

- 录制时只做分段标记
- 录制结束后再离线生成组合视频

## 设计原则

- 优先最小改动，不改变现有默认录制行为
- 分段功能必须是可选功能，不开启时现有流程保持不变
- 标记同时保存“时间戳”和“帧索引”，但导出时以帧索引为主
- 先支持 PC 端预览窗口按键分段，不优先改 Quest 端输入逻辑
- 原始录制产物不覆盖，只新增标记文件和导出目录

## 需求定义

### 用户视角

1. 操作员启动录制。
2. 录制自动进入第 1 段。
3. 操作员每按一次分段键，就进入下一段。
4. 操作员按 `q` 或 `Ctrl+C` 结束录制。
5. 录制结束后运行一个导出脚本，自动得到：
   - 第 1 段 + 第 2 段
   - 第 1 段 + 第 3 段
   - 第 1 段 + 第 4 段
   - 依次类推

### 数据语义

- “段”表示一个连续的时间区间
- 每一段对应原始视频中的连续帧区间
- 组合视频表示把多个段按给定顺序拼接成一个新视频
- 当前版本固定支持“第 1 段 + 第 N 段”的导出规则，但内部数据结构应支持未来扩展到任意组合

## 方案概览

### 1. 录制阶段新增分段标记

在 `scripts/record_quest_dataset.py` 中增加可选的分段模式。

建议新增参数：

- `--enable-segmentation`

启用后：

- 录制开始自动创建第 1 段
- 在预览窗口按 `n` 时切到下一段
- 在录制结束时自动补齐最后一段的结束信息

### 2. 新增分段标记文件

在数据集目录下新增：

- `segments.json`

建议结构示例：

```json
{
  "version": 1,
  "mode": "manual_keypress",
  "segment_key": "n",
  "segments": [
    {
      "segment_index": 1,
      "label": "seg1",
      "start_frame_index": 0,
      "end_frame_index": 152,
      "start_timestamp_ns": 123456789000,
      "end_timestamp_ns": 123456999000
    },
    {
      "segment_index": 2,
      "label": "seg2",
      "start_frame_index": 153,
      "end_frame_index": 287,
      "start_timestamp_ns": 123457000000,
      "end_timestamp_ns": 123457180000
    }
  ]
}
```

### 3. 录制后离线导出组合结果

新增脚本：

- `scripts/export_stage_combinations.py`

职责：

- 读取 `camera.mp4`
- 读取 `aligned_frames.parquet`
- 读取 `segments.json`
- 按“第 1 段 + 第 N 段”的规则导出多个新结果

建议输出目录：

- `data/<dataset>/exports/seg1_seg2/`
- `data/<dataset>/exports/seg1_seg3/`
- `data/<dataset>/exports/seg1_seg4/`

每个导出目录下建议包含：

- `camera.mp4`
- `aligned_frames.parquet`
- `export_manifest.json`

## 详细实现计划

### 一、数据结构与状态管理

在 `DatasetRecorder` 内增加分段状态：

- `segmentation_enabled`
- `current_segment_start_frame_index`
- `current_segment_start_timestamp_ns`
- `segments`

并补充一个获取“当前最新有效相机帧信息”的机制，至少能拿到：

- 最新 `camera_frame_index`
- 最新 `camera_timestamp_ns`

目的：

- 按下分段键时，将分段边界绑定到最近一个已经成功录制的相机帧
- 避免只用墙上时钟导致导出结果与视频帧不一致

### 二、录制交互改造

修改预览循环 `_run_preview_loop`：

- 保留 `q` 结束录制
- 新增 `n` 作为“下一段”

按下 `n` 时执行：

1. 结束当前段
2. 把当前最新帧作为当前段的结束边界
3. 立即开始下一段
4. 在日志中输出当前切段结果

边界行为：

- 如果还没有收到任何相机帧，则忽略分段按键并提示日志
- 如果重复按键导致空段，需要决定是否禁止生成空段

建议：

- 初版直接禁止空段
- 若 `start_frame_index > end_frame_index`，则不提交该段

### 三、录制结束收尾

在 `recorder.close()` 前或 `close()` 内完成最后一段封口：

- 如果分段功能开启且当前段尚未结束
- 使用最后一帧的 frame index 和 timestamp 作为该段结束边界

同时把 `segments.json` 写入数据集目录。

### 四、离线导出脚本

新增 `scripts/export_stage_combinations.py`，建议支持参数：

- `--name`
- `--output-root`
- `--include-aligned`

初版无需支持复杂规则，默认行为即可：

- 自动读取所有 segment
- 依次生成 `seg1 + segN`

导出流程：

1. 读取 `segments.json`
2. 校验至少存在 2 段
3. 打开原始 `camera.mp4`
4. 对每个目标组合构造要保留的 frame index 集合或区间列表
5. 顺序读取原视频并写入新视频
6. 过滤 `aligned_frames.parquet`，仅保留对应帧
7. 写出导出说明文件 `export_manifest.json`

### 五、导出数据对齐策略

视频切片与表格切片统一以 `camera_frame_index` 为准：

- 视频：按 frame index 选择并顺序写出
- `aligned_frames.parquet`：按相同 frame index 过滤并重建连续索引

建议在导出后的 parquet 中保留两套索引：

- `source_camera_frame_index`
- `export_camera_frame_index`

这样后续排查问题时能追溯回原始数据。

### 六、日志与元数据

建议在以下位置补充日志：

- 启动分段模式时
- 每次切段时
- 录制结束自动闭合最后一段时
- 导出每个组合视频开始/结束时

建议在 `session.json` 中追加可选字段：

- `segmentation_enabled`
- `segments_path`

这样回放或后续工具可以知道该 session 是否带分段标记。

## 预估改动文件

必改：

- `scripts/record_quest_dataset.py`
- 新增 `scripts/export_stage_combinations.py`

可选：

- `README.md`

当前不建议修改：

- `hand_tracking_streamer/Assets/Scripts/*`

原因：

- 本次需求完全可以先在 Python 录制端完成
- 不必把 Quest 端输入、UI 或网络协议一并拉进来

## 验收标准

### 功能验收

1. 不开启 `--enable-segmentation` 时，原有录制流程行为不变。
2. 开启 `--enable-segmentation` 后，按 `n` 能正确产生分段。
3. 结束录制后，数据集目录中能生成 `segments.json`。
4. 当录制出 4 段时，导出脚本能生成：
   - `seg1_seg2`
   - `seg1_seg3`
   - `seg1_seg4`
5. 每个导出目录内的视频帧数与导出的 `aligned_frames.parquet` 行数一致。

### 最小验证

- 运行录制脚本 `--help`
- 运行导出脚本 `--help`
- 使用一段短样例录制，手动按 2 到 3 次分段键
- 检查 `segments.json` 内容是否连续、边界是否合理
- 检查导出结果能否正常播放

## 风险与注意事项

### 1. 只记时间戳不够稳

如果只记录“按键时刻的系统时间”，可能无法准确映射到视频帧边界。因此必须同时记录：

- 帧索引
- 帧时间戳

### 2. 空段与极短段

操作员连续快速按键时，可能产生空段或只有 1 帧的极短段。初版建议：

- 空段丢弃
- 极短段允许保留，但在日志中提示

### 3. 原始 telemetry 的切片

初版优先保证：

- 视频导出正确
- `aligned_frames.parquet` 导出正确

`telemetry_raw.parquet` 是否同步导出可放到第二阶段，因为它不是一帧一行，过滤策略更复杂。

### 4. 组合规则的泛化

当前需求是“第 1 段 + 后续每一段”。实现时不要把内部结构写死成只支持这一个规则，便于后续扩展到：

- 任意两段组合
- 多段拼接
- 跳过某些段

## 开发顺序建议

1. 先改 `record_quest_dataset.py`，完成分段状态记录与 `segments.json` 输出
2. 再实现 `export_stage_combinations.py`
3. 最后补 `README.md` 的使用说明

## 非目标

本次计划不包含以下内容：

- 在 Quest 端增加“分段按钮”或手势交互
- 在录制过程中实时生成多个输出视频
- 修改现有网络协议
- 导出所有 raw telemetry 的完整分段副本

## 结论

本方案的核心是：

- 录制时只负责“标记段边界”
- 导出时负责“按段组合生成新视频”

这是当前仓库里最小、最稳、最容易验证的实现路径，也最符合现有 `camera.mp4 + aligned_frames.parquet` 的数据组织方式。
