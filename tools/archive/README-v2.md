# Clone Voice v2 使用说明

## 概述

`clone-voice-v2.py` 是一个基于JSON输入的TTS语音克隆脚本，支持多段文本批量合成，每段文本可以包含独立的描述信息。

## 主要特性

- ✅ JSON格式输入，结构化配置
- ✅ 支持多段文本批量处理
- ✅ 每段文本独立描述
- ✅ 支持语音克隆（参考音频）
- ✅ 灵活的输出文件命名模式
- ✅ 干运行模式（--dry-run）预览
- ✅ 完整的参数验证

## 安装要求

```bash
# 确保已激活虚拟环境（必须！）
& D:\tony\bukreedor\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

## JSON输入格式

### 基本结构

```json
{
  "tts-model": "模型名称",
  "reference_audio": "参考音频路径（可选）",
  "segments": [
    {
      "text": "要合成的文本",
      "desc": "描述信息（可选）"
    }
  ]
}
```

### 完整示例

```json
{
  "tts-model": "qwen3-tts-12hz-0.6b-base",
  "reference_audio": "../samples/voice-lyx-30s.mp3",
  "segments": [
    {
      "text": "六王毕，四海一，蜀山兀，阿房出。覆压三百余里，隔离天日。",
      "desc": "仅以标点符号断句"
    },
    {
      "text": "覆压三百余里，隔离天日。",
      "desc": "仅以标点符号断句，夹杂轻笑"
    },
    {
      "text": "五步一楼，十步一阁；廊腰缦回，檐牙高啄；各抱地势，钩心斗角。",
      "desc": "仅以标点符号断句，声音越来越紧张"
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `tts-model` | string | ✅ | TTS模型名称，必须是tts-profiles.yaml中定义的模型 |
| `reference_audio` | string | ❌ | 参考音频路径，用于语音克隆 |
| `segments` | array | ✅ | 文本段落数组 |
| `segments[].text` | string | ✅ | 要合成的文本内容 |
| `segments[].desc` | string | ❌ | 段落描述，用于记录和说明 |

## 命令行参数

### 必需参数

- `-i, --input`: 输入JSON文件路径
- `-o, --output`: 输出文件路径模式

### 可选参数

- `-p, --profile`: TTS配置文件路径（默认：tts-profiles.yaml）
- `--hf-mirror`: HuggingFace镜像URL（用于加速下载）
- `--language`: 语言设置（默认：Chinese）
- `--dry-run`: 干运行模式，只显示将要执行的操作而不实际合成
- 其他模型特定参数（根据模型配置自动添加）

## 输出文件命名模式

### 使用 %%02d

```bash
python clone-voice-v2.py -i input.json -o output/阿房宫赋-%%02d.mp3
```

输出文件：
- `output/阿房宫赋-01.mp3`
- `output/阿房宫赋-02.mp3`
- `output/阿房宫赋-03.mp3`
- ...

### 使用 %%03d

```bash
python clone-voice-v2.py -i input.json -o output/阿房宫赋-%%03d.mp3
```

输出文件：
- `output/阿房宫赋-001.mp3`
- `output/阿房宫赋-002.mp3`
- `output/阿房宫赋-003.mp3`
- ...

### 使用 %%d

```bash
python clone-voice-v2.py -i input.json -o output/阿房宫赋-%%d.mp3
```

输出文件：
- `output/阿房宫赋-1.mp3`
- `output/阿房宫赋-2.mp3`
- `output/阿房宫赋-3.mp3`
- ...

## 使用示例

### 基本使用

```bash
# 激活虚拟环境
& D:\tony\bukreedor\.venv\Scripts\Activate.ps1

# 基本合成
python clone-voice-v2.py -i example-epang-palace.json -o output/阿房宫赋-%%02d.mp3
```

### 使用语音克隆

```json
{
  "tts-model": "qwen3-tts-12hz-0.6b-base",
  "reference_audio": "../samples/voice-lyx-30s.mp3",
  "segments": [
    {
      "text": "这是用克隆声音合成的语音。",
      "desc": "使用参考音频克隆声音"
    }
  ]
}
```

```bash
python clone-voice-v2.py -i input.json -o output/克隆声音-%%02d.mp3
```

### 干运行模式（预览）

```bash
# 只显示将要执行的操作，不实际合成
python clone-voice-v2.py -i example-epang-palace.json -o output/阿房宫赋-%%02d.mp3 --dry-run
```

### 自定义参数

```bash
# 使用自定义温度和速度参数
python clone-voice-v2.py -i input.json -o output/阿房宫赋-%%02d.mp3 --temperature 0.8 --speed 1.2
```

### 批量处理多个JSON文件

```bash
# Windows PowerShell
Get-ChildItem -Path input -Filter *.json | ForEach-Object {
    $output = "output/$($_.BaseName)-%%02d.mp3"
    python clone-voice-v2.py -i $_.FullName -o $output
}
```

## 错误处理

### 常见错误

1. **JSON格式错误**
   ```
   Error: Invalid JSON format in input.json: Expecting property name enclosed in double quotes
   ```
   解决：检查JSON格式是否正确，使用JSON验证工具

2. **缺少必需字段**
   ```
   Error: Missing required field: tts-model
   ```
   解决：确保JSON包含 `tts-model` 和 `segments` 字段

3. **模型不存在**
   ```
   Error: Unknown model 'invalid-model'
   Available models: qwen3-tts-12hz-0.6b-base, ...
   ```
   解决：使用正确的模型名称，参考 tts-profiles.yaml

4. **参考音频不存在**
   ```
   Error: Reference audio file not found: ../samples/voice-lyx-30s.mp3
   ```
   解决：确保参考音频路径正确且文件存在

5. **输出模式不包含编号**
   ```
   Warning: Output pattern 'output.mp3' does not contain %%02d or %%03d
   ```
   解决：在输出模式中添加 %%02d 或 %%03d

## 最佳实践

1. **JSON文件组织**
   - 将相关的JSON文件放在同一目录
   - 使用有意义的文件名（如：chapter-01.json, chapter-02.json）

2. **输出文件命名**
   - 使用 %%02d 或 %%03d 确保文件排序正确
   - 包含项目名称和章节信息
   - 示例：`output/阿房宫赋-第%%02d段.mp3`

3. **段落描述**
   - 为每个段落添加描述，便于后续管理
   - 描述可以包含情感、语气、停顿等信息
   - 示例：`"desc": "仅以标点符号断句，声音越来越紧张"`

4. **测试验证**
   - 使用 --dry-run 模式先预览
   - 先用少量段落测试
   - 验证输出质量和参数设置

5. **批量处理**
   - 使用脚本批量处理多个JSON文件
   - 记录处理日志
   - 定期备份输出文件

## 与 v1 的区别

| 特性 | v1 | v2 |
|------|----|----|
| 输入格式 | 文本文件 (.txt) | JSON文件 |
| 多段落支持 | 自动分段 | 显式定义 |
| 段落描述 | 不支持 | 支持 |
| 输出命名 | 固定模式 | 灵活模式 |
| 语音克隆 | 命令行参数 | JSON配置 |
| 干运行 | 不支持 | 支持 |

## 支持的TTS模型

查看 `tts-profiles.yaml` 获取完整的模型列表：

```bash
# 查看可用模型
python clone-voice-v2.py --help
```

常见模型：
- `qwen3-tts-12hz-0.6b-base`: Qwen3-TTS 基础模型
- `qwen3-tts-12hz-0.6b-sft`: Qwen3-TTS 微调模型
- 其他模型根据配置文件定义

## 性能优化

1. **GPU加速**
   - 确保CUDA可用
   - 使用GPU模型获得更快速度

2. **批量处理**
   - 一次性处理多个段落
   - 避免重复加载模型

3. **输出格式**
   - 选择合适的音频格式
   - 考虑文件大小和质量平衡

## 故障排除

### 合成失败

1. 检查模型是否正确加载
2. 验证输入文本格式
3. 查看错误日志
4. 尝试简化文本重新测试

### 音质问题

1. 检查参考音频质量
2. 调整模型参数
3. 尝试不同的模型变体
4. 优化文本分段

### 性能问题

1. 确保使用GPU
2. 减少段落长度
3. 调整批处理大小
4. 关闭不必要的程序

## 示例文件

项目包含以下示例文件：

- `example-epang-palace.json`: 阿房宫赋示例
- `example-basic.json`: 基本使用示例
- `example-voice-clone.json`: 语音克隆示例

## 贡献

欢迎提交问题和改进建议！

## 许可证

根据项目许可证使用。