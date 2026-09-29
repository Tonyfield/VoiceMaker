# VoxCPM2 安装和使用指南

## 当前状态

✅ **VoxCPM2 集成已完成**
- ✅ 模型实现已完成
- ✅ 工厂模式已集成
- ✅ 配置文件已更新
- ✅ 文档已完善
- ✅ 测试脚本已创建

## 安装步骤

### 1. 安装 VoxCPM 包

```bash
# 激活虚拟环境（必须！）
& D:\tony\bukreedor\.venv\Scripts\Activate.ps1

# 安装 VoxCPM
pip install voxcpm
```

### 2. 下载 VoxCPM2 模型

VoxCPM2 模型会自动从 ModelScope 下载（中国镜像，速度更快）。有两种方式：

#### 方式 1：自动下载（推荐）

模型会在首次使用时自动从 ModelScope 下载，无需手动操作。

#### 方式 2：手动下载

如果自动下载失败，可以手动下载：

```bash
# 创建模型目录
mkdir D:\llm-models\VoxCPM2

# 从 ModelScope 下载模型（推荐，中国镜像）
git clone https://www.modelscope.cn/OpenBMB/VoxCPM2.git D:\llm-models\VoxCPM2
```

或者访问 ModelScope 页面：
- **ModelScope**: https://modelscope.cn/models/OpenBMB/VoxCPM2
- 下载所有文件到 `D:\llm-models\VoxCPM2`

### 3. 验证安装

运行测试脚本：

```bash
python test-voxcpm2.py
```

预期输出：
```
============================================================
Testing VoxCPM2 Integration
============================================================
✅ VoxCPM2 model found in profile
✅ Model name: OpenBMB/VoxCPM2
✅ Framework: voxcpm2
✅ Description: VoxCPM2 - Tokenizer-Free TTS with voice design and cloning supports 30+ languages and 9 dialects
✅ Supported parameters:
   - language: Language for synthesis
   - dialect: Dialect for synthesis (optional)
   - emotion: Emotion type for speech synthesis
   - speed: Speech speed multiplier
   - pitch: Pitch shift multiplier
   - energy: Energy level (0.0-1.0)
   - brightness: Brightness level (0.0-1.0)
   - voice_clone_audio: Path to reference audio file for voice cloning (optional)
   - output_format: Output audio format
   - output_sample_rate: Output sample rate
============================================================
Testing Factory Creation
============================================================
Attempting to create VoxCPM2 model instance...
Note: This will fail if voxcpm is not installed or model not downloaded
2026-05-09 21:26:52 | INFO     | 📦 Loading VoxCPM2 model...
voxcpm_model_path: D:\llm-models\VoxCPM2 zipenhancer_model_path: iic/speech_zipenhancer_ans_multiloss_16k_base enable_denoiser: True
2026-05-09 21:26:52 | SUCCESS  | 🎉 VoxCPM2 model loaded successfully
✅ VoxCPM2 model instance created successfully
   Model type: VoxCPM2Model
============================================================
Integration Test Complete
============================================================
```

## 使用示例

### 基本使用

创建 JSON 文件 (`input.json`):

```json
{
  "tts-model": "voxcpm2",
  "reference_audio": "../samples/voice-lyx-30s.mp3",
  "segments": [
    {
      "text": "欢迎使用VoxCPM2语音合成系统。",
      "desc": "使用默认语音"
    }
  ]
}
```

运行合成：

```bash
python clone-voice-v2.py -i input.json -o output/voxcpm2-%%02d.wav
```

### 带语音设计参数

```bash
python clone-voice-v2.py -i input.json -o output/voxcpm2-%%02d.wav \
  --pitch 1.2 \
  --speed 1.1 \
  --energy 0.8 \
  --brightness 0.7
```

### 带语言和方言

```bash
python clone-voice-v2.py -i input.json -o output/voxcpm2-%%02d.wav \
  --language zh \
  --dialect mandarin
```

## 支持的参数

### 语音设计参数

| 参数 | 类型 | 范围 | 默认值 | 说明 |
|------|------|-------|---------|------|
| `--pitch` | float | 0.8-1.5 | 1.0 | 音调倍数 |
| `--speed` | float | 0.5-2.0 | 1.0 | 语速倍数 |
| `--energy` | float | 0.0-1.0 | 1.0 | 能量级别 |
| `--brightness` | float | 0.0-1.0 | 1.0 | 亮度级别 |

### 语言参数

| 参数 | 类型 | 选项 | 默认值 | 说明 |
|------|------|------|---------|------|
| `--language` | str | zh, en, ja, ko, es, fr, de, ru, ar, pt | zh | 合成语言 |
| `--dialect` | str | mandarin, cantonese, shanghainese, sichuanese, american, british, australian, castilian, mexican, argentinian | null | 合成方言 |

### 情感参数

| 参数 | 类型 | 选项 | 默认值 | 说明 |
|------|------|------|---------|------|
| `--emotion` | str | neutral, happy, sad, angry, tender | neutral | 情感类型 |

### 输出参数

| 参数 | 类型 | 选项 | 默认值 | 说明 |
|------|------|------|---------|------|
| `--output-format` | str | wav, mp3, flac | wav | 输出格式 |
| `--output-sample-rate` | int | 16000, 22050, 24000, 44100, 48000 | 48000 | 采样率 |

## 故障排除

### 问题 1: "No module named 'voxcpm'"

**解决方案**:
```bash
pip install voxcpm
```

### 问题 2: "No such file or directory: 'D:\\llm-models\\VoxCPM2\\config.json'"

**解决方案**:
```bash
# 创建模型目录
mkdir D:\llm-models\VoxCPM2

# 从 ModelScope 下载模型（推荐）
git clone https://www.modelscope.cn/OpenBMB/VoxCPM2.git D:\llm-models\VoxCPM2
```

或者访问 ModelScope 页面：
- **ModelScope**: https://modelscope.cn/models/OpenBMB/VoxCPM2
- 下载所有文件到 `D:\llm-models\VoxCPM2`

### 问题 3: CUDA out of memory

**解决方案**:
- 使用 FP8 量化版本（仅需 2GB GPU 显存）
- 减少批处理大小
- 清理 GPU 缓存

### 问题 4: 推理速度慢

**解决方案**:
- 确保 GPU 正在使用
- 使用 FP8 或 BF16 精度
- 启用量化
- 增加批处理大小

## 模型变体

| 变体 | 精度 | GPU 显存 | 质量 | 速度 |
|------|------|---------|------|------|
| VoxCPM2-FP8 | FP8 | 2GB | 好 | 最快 |
| VoxCPM2-BF16 | BF16 | 8GB | 更好 | 快 |
| VoxCPM2-FP32 | FP32 | 16GB | 最好 | 慢 |

## 性能优化

1. **使用 FP8 进行低资源场景**: 仅需 2GB GPU 显存
2. **批处理**: 高效处理多个段落
3. **清理 GPU 缓存**: 定期清理大批处理后的缓存
4. **选择合适的格式**: WAV 用于质量，MP3 用于文件大小

## 资源

- **GitHub**: https://github.com/OpenBMB/VoxCPM
- **ModelScope**: https://modelscope.cn/models/OpenBMB/VoxCPM2
- **官方网站**: https://voxcpm.modelbest.cn
- **文档**: https://docs.voxcpm.modelbest.cn
- **演示**: https://demo.voxcpm.modelbest.cn

## 许可证

Apache 2.0 许可证 - 可免费用于商业和个人用途。

## 支持

如有问题或疑问：
- GitHub Issues: https://github.com/OpenBMB/VoxCPM/issues
- 查看 [VoxCPM2 指南](../.trae/skills/tts-model-guide/reference/voxcpm-guide.md) 获取详细文档

## 总结

VoxCPM2 已成功集成到 VoiceCloner 中，包含：
- ✅ 完整的模型实现
- ✅ 工厂模式集成
- ✅ 全面的配置
- ✅ 完整的文档
- ✅ 示例文件
- ✅ 测试脚本
- ✅ 使用指南

集成已准备就绪，安装 VoxCPM 包和下载模型后即可立即使用！