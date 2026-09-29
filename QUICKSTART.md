# Clone Voice v2 快速开始指南

## 快速开始

### 1. 激活虚拟环境（必须！）

```powershell
& D:\tony\bukreedor\.venv\Scripts\Activate.ps1
```

### 2. 验证JSON文件

```powershell
# 验证单个文件
python validate-json.py example-epang-palace.json

# 验证所有JSON文件
python validate-json.py -d .
```

### 3. 干运行（预览）

```powershell
# 查看将要执行的操作，不实际合成
python clone-voice-v2.py -i example-epang-palace.json -o output/阿房宫赋-%%02d.mp3 --dry-run
```

### 4. 执行合成

```powershell
# 合成语音
python clone-voice-v2.py -i example-epang-palace.json -o output/阿房宫赋-%%02d.mp3
```

### 5. 批量处理

```powershell
# 处理所有JSON文件
python batch-process.py -d . -o output
```

## JSON文件模板

### 基本模板

```json
{
  "tts-model": "qwen3-tts-12hz-0.6b-base",
  "segments": [
    {
      "text": "第一段文本",
      "desc": "描述信息"
    },
    {
      "text": "第二段文本",
      "desc": "描述信息"
    }
  ]
}
```

### 带语音克隆的模板

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

## 输出文件命名

### 使用 %%02d（推荐）

```powershell
python clone-voice-v2.py -i input.json -o output/文件名-%%02d.mp3
```

输出：
- `output/文件名-01.mp3`
- `output/文件名-02.mp3`
- `output/文件名-03.mp3`

### 使用 %%03d

```powershell
python clone-voice-v2.py -i input.json -o output/文件名-%%03d.mp3
```

输出：
- `output/文件名-001.mp3`
- `output/文件名-002.mp3`
- `output/文件名-003.mp3`

## 常用命令

### 查看帮助

```powershell
python clone-voice-v2.py --help
python batch-process.py --help
python validate-json.py --help
```

### 自定义参数

```powershell
# 调整温度和速度
python clone-voice-v2.py -i input.json -o output/%%02d.mp3 --temperature 0.8 --speed 1.2
```

### 批量处理特定文件

```powershell
# 处理特定模式的文件
python batch-process.py -d . -o output -p "chapter-*.json"
```

## 工作流程

1. **准备JSON文件** - 根据模板创建JSON文件
2. **验证JSON** - 使用 `validate-json.py` 验证格式
3. **干运行** - 使用 `--dry-run` 预览
4. **执行合成** - 运行 `clone-voice-v2.py`
5. **检查结果** - 查看输出目录中的音频文件

## 示例文件

项目包含以下示例：

- `example-basic.json` - 基本使用示例
- `example-voice-clone.json` - 语音克隆示例
- `example-epang-palace.json` - 阿房宫赋完整示例

## 故障排除

### 问题：虚拟环境未激活

**错误信息**：
```
ModuleNotFoundError: No module named 'src'
```

**解决方法**：
```powershell
& D:\tony\bukreedor\.venv\Scripts\Activate.ps1
```

### 问题：JSON格式错误

**错误信息**：
```
Error: Invalid JSON format in input.json
```

**解决方法**：
```powershell
# 验证JSON格式
python validate-json.py input.json
```

### 问题：模型不存在

**错误信息**：
```
Error: Unknown model 'invalid-model'
```

**解决方法**：
查看 `tts-profiles.yaml` 中的可用模型列表

### 问题：参考音频不存在

**错误信息**：
```
Error: Reference audio file not found: ../samples/voice-lyx-30s.mp3
```

**解决方法**：
检查参考音频路径是否正确

## 最佳实践

1. **始终先验证JSON** - 在合成前使用 `validate-json.py`
2. **使用干运行** - 用 `--dry-run` 预览操作
3. **合理分段** - 每段文本不宜过长
4. **添加描述** - 为每段文本添加描述信息
5. **备份文件** - 定期备份JSON和输出文件

## 下一步

- 阅读完整文档：[README-v2.md](README-v2.md)
- 查看示例文件：`example-*.json`
- 了解TTS模型：查看 `tts-profiles.yaml`

## 获取帮助

遇到问题？
1. 查看错误信息
2. 阅读文档
3. 检查示例文件
4. 使用 `--help` 查看命令选项