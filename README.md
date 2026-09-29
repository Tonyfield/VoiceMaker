# VoiceCloner 工具集

完整的TTS语音克隆工具集，支持JSON配置、批量处理和语音克隆。

## 📁 项目结构

```
VoiceCloner/
├── clone-voice-v1.py          # v1版本：文本文件输入
├── clone-voice-v2.py          # v2版本：JSON输入（推荐）
├── batch-process.py           # Python批处理脚本
├── batch-process.ps1          # PowerShell批处理脚本
├── validate-json.py           # JSON验证工具
├── tts-profiles.yaml          # TTS模型配置
├── src/                       # 源代码模块
│   ├── tts_profile.py
│   ├── tts_factory.py
│   ├── qwen3_tts_model.py
│   ├── indextts2_model.py
│   ├── text_segmenter.py
│   └── ssml_parser.py
├── example-*.json             # 示例JSON文件
├── README-v2.md               # v2详细文档
├── QUICKSTART.md              # 快速开始指南
└── README.md                  # 本文件
```

## 🚀 快速开始

### 1. 激活虚拟环境（必须！）

```powershell
& D:\tony\bukreedor\.venv\Scripts\Activate.ps1
```

### 2. 选择使用方式

#### 方式A：使用 clone-voice-v2.py（推荐）

```powershell
# 验证JSON
python validate-json.py example-epang-palace.json

# 干运行预览
python clone-voice-v2.py -i example-epang-palace.json -o output/阿房宫赋-%%02d.mp3 --dry-run

# 执行合成
python clone-voice-v2.py -i example-epang-palace.json -o output/阿房宫赋-%%02d.mp3
```

#### 方式B：使用批处理脚本

```powershell
# Python批处理
python batch-process.py -d . -o output

# PowerShell批处理
.\batch-process.ps1 -InputDir . -OutputDir output
```

## 📖 工具说明

### clone-voice-v2.py

**主要特性**：
- ✅ JSON格式输入，结构化配置
- ✅ 支持多段文本批量处理
- ✅ 每段文本独立描述
- ✅ 支持语音克隆
- ✅ 灵活的输出文件命名
- ✅ 干运行模式预览

**基本用法**：
```powershell
python clone-voice-v2.py -i input.json -o output/文件名-%%02d.mp3
```

**详细文档**：[README-v2.md](README-v2.md)

### batch-process.py

**主要特性**：
- ✅ 批量处理多个JSON文件
- ✅ 自动生成输出文件名
- ✅ 支持干运行模式
- ✅ 错误处理和继续选项

**基本用法**：
```powershell
python batch-process.py -d . -o output
```

**高级用法**：
```powershell
# 处理特定模式的文件
python batch-process.py -d . -o output -p "chapter-*.json"

# 干运行预览
python batch-process.py -d . -o output --dry-run

# 带额外参数
python batch-process.py -d . -o output -- --temperature 0.8
```

### batch-process.ps1

**主要特性**：
- ✅ PowerShell原生批处理
- ✅ 自动激活虚拟环境
- ✅ 彩色输出和进度显示
- ✅ 错误处理

**基本用法**：
```powershell
.\batch-process.ps1 -InputDir . -OutputDir output
```

**高级用法**：
```powershell
# 干运行
.\batch-process.ps1 -InputDir . -OutputDir output -DryRun

# 遇到错误继续
.\batch-process.ps1 -InputDir . -OutputDir output -ContinueOnError

# 自定义文件模式
.\batch-process.ps1 -InputDir . -OutputDir output -Pattern "chapter-*.json"
```

### validate-json.py

**主要特性**：
- ✅ JSON格式验证
- ✅ 结构完整性检查
- ✅ 模型名称验证
- ✅ 参考音频文件检查

**基本用法**：
```powershell
# 验证单个文件
python validate-json.py input.json

# 验证多个文件
python validate-json.py file1.json file2.json file3.json

# 验证目录中所有JSON
python validate-json.py -d .

# 详细输出
python validate-json.py -v input.json
```

## 📝 JSON文件格式

### 基本结构

```json
{
  "tts-model": "qwen3-tts-12hz-0.6b-base",
  "reference_audio": "../samples/voice-lyx-30s.mp3",
  "segments": [
    {
      "text": "要合成的文本",
      "desc": "描述信息"
    }
  ]
}
```

### 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `tts-model` | string | ✅ | TTS模型名称 |
| `reference_audio` | string | ❌ | 参考音频路径 |
| `segments` | array | ✅ | 文本段落数组 |
| `segments[].text` | string | ✅ | 要合成的文本 |
| `segments[].desc` | string | ❌ | 段落描述 |

### 完整示例

```json
{
  "tts-model": "qwen3-tts-12hz-0.6b-base",
  "reference_audio": "../samples/voice-lyx-30s.mp3",
  "segments": [
    {
      "text": "六王毕，四海一，蜀山兀，阿房出。",
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

## 📤 输出文件命名

### 使用 %%02d（推荐）

```powershell
python clone-voice-v2.py -i input.json -o output/阿房宫赋-%%02d.mp3
```

输出：
- `output/阿房宫赋-01.mp3`
- `output/阿房宫赋-02.mp3`
- `output/阿房宫赋-03.mp3`

### 使用 %%03d

```powershell
python clone-voice-v2.py -i input.json -o output/阿房宫赋-%%03d.mp3
```

输出：
- `output/阿房宫赋-001.mp3`
- `output/阿房宫赋-002.mp3`
- `output/阿房宫赋-003.mp3`

## 🎯 工作流程

### 标准流程

1. **准备JSON文件**
   ```powershell
   # 根据模板创建JSON文件
   # 或修改示例文件
   ```

2. **验证JSON**
   ```powershell
   python validate-json.py input.json
   ```

3. **干运行预览**
   ```powershell
   python clone-voice-v2.py -i input.json -o output/%%02d.mp3 --dry-run
   ```

4. **执行合成**
   ```powershell
   python clone-voice-v2.py -i input.json -o output/%%02d.mp3
   ```

5. **检查结果**
   ```powershell
   # 查看输出目录
   Get-ChildItem output
   ```

### 批量处理流程

1. **准备多个JSON文件**
   ```powershell
   # 将所有JSON文件放在同一目录
   ```

2. **验证所有文件**
   ```powershell
   python validate-json.py -d .
   ```

3. **批量处理**
   ```powershell
   # 使用Python脚本
   python batch-process.py -d . -o output
   
   # 或使用PowerShell脚本
   .\batch-process.ps1 -InputDir . -OutputDir output
   ```

4. **检查结果**
   ```powershell
   Get-ChildItem output -Recurse
   ```

## 📚 示例文件

项目包含以下示例文件：

| 文件名 | 说明 |
|--------|------|
| `example-basic.json` | 基本使用示例 |
| `example-voice-clone.json` | 语音克隆示例 |
| `example-epang-palace.json` | 阿房宫赋完整示例 |

## 🔧 常用命令

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

## ⚠️ 故障排除

### 问题：虚拟环境未激活

**错误**：
```
ModuleNotFoundError: No module named 'src'
```

**解决**：
```powershell
& D:\tony\bukreedor\.venv\Scripts\Activate.ps1
```

### 问题：JSON格式错误

**错误**：
```
Error: Invalid JSON format in input.json
```

**解决**：
```powershell
python validate-json.py input.json
```

### 问题：模型不存在

**错误**：
```
Error: Unknown model 'invalid-model'
```

**解决**：
查看 `tts-profiles.yaml` 中的可用模型

### 问题：参考音频不存在

**错误**：
```
Error: Reference audio file not found: ../samples/voice-lyx-30s.mp3
```

**解决**：
检查参考音频路径是否正确

## 💡 最佳实践

1. **始终先验证JSON**
   - 使用 `validate-json.py` 验证格式
   - 检查模型名称是否正确
   - 确认参考音频存在

2. **使用干运行**
   - 用 `--dry-run` 预览操作
   - 验证输出文件名
   - 检查参数设置

3. **合理分段**
   - 每段文本不宜过长
   - 根据内容逻辑分段
   - 添加描述信息

4. **批量处理**
   - 使用批处理脚本提高效率
   - 处理前先验证所有文件
   - 定期备份输出文件

5. **资源管理**
   - 确保GPU可用
   - 监控磁盘空间
   - 定期清理临时文件

## 📖 文档

- [README-v2.md](README-v2.md) - clone-voice-v2.py 详细文档
- [QUICKSTART.md](QUICKSTART.md) - 快速开始指南
- [tts-profiles.yaml](tts-profiles.yaml) - TTS模型配置

## 🆚 v1 vs v2 对比

| 特性 | v1 | v2 |
|------|----|----|
| 输入格式 | 文本文件 (.txt) | JSON文件 |
| 多段落支持 | 自动分段 | 显式定义 |
| 段落描述 | 不支持 | 支持 |
| 输出命名 | 固定模式 | 灵活模式 |
| 语音克隆 | 命令行参数 | JSON配置 |
| 干运行 | 不支持 | 支持 |
| 批处理 | 通配符模式 | JSON列表 |

## 🎓 学习资源

- TTS模型指导：[tts-model-guide](../.trae/skills/tts-model-guide/)
- SSML语法：[ssml-tts-guide](../.trae/skills/ssml-tts-guide/)

## 🤝 贡献

欢迎提交问题和改进建议！

## 📄 许可证

根据项目许可证使用。