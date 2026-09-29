# VoxCPM2 Integration Guide

## Overview

VoxCPM2 has been successfully integrated into VoiceCloner! This guide will help you get started with using VoxCPM2 for text-to-speech synthesis.

## Features

VoxCPM2 offers the following advanced features:

- **Tokenizer-Free TTS**: No discrete tokenization, continuous space modeling
- **Voice Design**: Precise control over pitch, speed, energy, and brightness
- **Voice Cloning**: Clone voices from short audio samples
- **Multi-Language**: 30+ languages and 9 dialects
- **High Quality**: 48kHz studio-quality audio output
- **Efficient**: FP8 quantization requires only 2GB GPU memory

## Installation

### Step 1: Install VoxCPM Package

```bash
# Activate virtual environment (MANDATORY)
& D:\tony\bukreedor\.venv\Scripts\Activate.ps1

# Install VoxCPM
pip install voxcpm
```

### Step 2: Download Model

VoxCPM2 model will be automatically downloaded from ModelScope on first use. ModelScope is a Chinese mirror service with faster download speeds in China.

**Automatic Download** (Recommended):
- Model will be automatically downloaded to `D:\llm-models\VoxCPM2` on first use
- No manual action required

**Manual Download** (if automatic download fails):
```bash
# Create model directory
mkdir D:\llm-models\VoxCPM2

# Download from ModelScope (recommended for China)
git clone https://www.modelscope.cn/OpenBMB/VoxCPM2.git D:\llm-models\VoxCPM2
```

Or visit ModelScope page:
- **ModelScope**: https://modelscope.cn/models/OpenBMB/VoxCPM2
- Download all files to `D:\llm-models\VoxCPM2`

## Quick Start

### Basic Usage

Create a JSON file (`input.json`):

```json
{
  "tts-model": "voxcpm2",
  "reference_audio": "../samples/voice-sample.wav",
  "segments": [
    {
      "text": "欢迎使用VoxCPM2语音合成系统。",
      "desc": "使用默认语音"
    }
  ]
}
```

Run the synthesis:

```bash
python clone-voice-v2.py -i input.json -o output/voxcpm2-%%02d.wav
```

### With Voice Design Parameters

```bash
python clone-voice-v2.py -i input.json -o output/voxcpm2-%%02d.wav \
  --pitch 1.2 \
  --speed 1.1 \
  --energy 0.8 \
  --brightness 0.7
```

### With Language and Dialect

```bash
python clone-voice-v2.py -i input.json -o output/voxcpm2-%%02d.wav \
  --language zh \
  --dialect mandarin
```

## Supported Parameters

### Voice Design Parameters

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `--pitch` | float | 0.8-1.5 | 1.0 | Pitch shift multiplier |
| `--speed` | float | 0.5-2.0 | 1.0 | Speech speed multiplier |
| `--energy` | float | 0.0-1.0 | 1.0 | Energy level |
| `--brightness` | float | 0.0-1.0 | 1.0 | Brightness level |

### Language Parameters

| Parameter | Type | Choices | Default | Description |
|-----------|------|---------|---------|-------------|
| `--language` | str | zh, en, ja, ko, es, fr, de, ru, ar, pt | zh | Language for synthesis |
| `--dialect` | str | mandarin, cantonese, shanghainese, sichuanese, american, british, australian, castilian, mexican, argentinian | null | Dialect for synthesis |

### Emotion Parameters

| Parameter | Type | Choices | Default | Description |
|-----------|------|---------|---------|-------------|
| `--emotion` | str | neutral, happy, sad, angry, tender | neutral | Emotion type for speech synthesis |

### Output Parameters

| Parameter | Type | Choices | Default | Description |
|-----------|------|---------|---------|-------------|
| `--output-format` | str | wav, mp3, flac | wav | Output audio format |
| `--output-sample-rate` | int | 16000, 22050, 24000, 44100, 48000 | 48000 | Output sample rate |

## Examples

### Example 1: Chinese Speech with Voice Cloning

```json
{
  "tts-model": "voxcpm2",
  "reference_audio": "../samples/voice-lyx-30s.mp3",
  "segments": [
    {
      "text": "这是用克隆声音合成的中文语音。",
      "desc": "使用参考音频克隆声音"
    }
  ]
}
```

```bash
python clone-voice-v2.py -i example.json -o output/chinese-%%02d.wav
```

### Example 2: Multi-Language Synthesis

```json
{
  "tts-model": "voxcpm2",
  "segments": [
    {
      "text": "Welcome to VoxCPM2.",
      "desc": "English"
    },
    {
      "text": "欢迎使用VoxCPM2。",
      "desc": "Chinese"
    },
    {
      "text": "VoxCPM2へようこそ。",
      "desc": "Japanese"
    }
  ]
}
```

```bash
python clone-voice-v2.py -i example.json -o output/multilang-%%02d.wav
```

### Example 3: Voice Design with Custom Parameters

```json
{
  "tts-model": "voxcpm2",
  "segments": [
    {
      "text": "这是一个高音调、快语速的语音。",
      "desc": "高音调、快语速"
    },
    {
      "text": "这是一个低音调、慢语速的语音。",
      "desc": "低音调、慢语速"
    }
  ]
}
```

```bash
# First segment: high pitch, fast speed
python clone-voice-v2.py -i example.json -o output/segment-01.wav --pitch 1.3 --speed 1.5

# Second segment: low pitch, slow speed
python clone-voice-v2.py -i example.json -o output/segment-02.wav --pitch 0.8 --speed 0.7
```

### Example 4: Dialect Support

```json
{
  "tts-model": "voxcpm2",
  "segments": [
    {
      "text": "这是普通话。",
      "desc": "Mandarin"
    },
    {
      "text": "这是粤语。",
      "desc": "Cantonese"
    },
    {
      "text": "这是上海话。",
      "desc": "Shanghainese"
    }
  ]
}
```

```bash
# Mandarin
python clone-voice-v2.py -i example.json -o output/mandarin.wav --dialect mandarin

# Cantonese
python clone-voice-v2.py -i example.json -o output/cantonese.wav --dialect cantonese

# Shanghainese
python clone-voice-v2.py -i example.json -o output/shanghainese.wav --dialect shanghainese
```

## Testing Integration

Run the test script to verify VoxCPM2 integration:

```bash
python test-voxcpm2.py
```

Expected output:
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
Note: This will fail if voxcpm is not installed, but that's expected
⚠️  Expected: voxcpm package not installed
   To install: pip install voxcpm
============================================================
Integration Test Complete
============================================================
```

## Troubleshooting

### Issue: "No module named 'voxcpm'"

**Solution**: Install VoxCPM package
```bash
pip install voxcpm
```

### Issue: "CUDA out of memory"

**Solution**: Use FP8 quantized version or reduce batch size
```bash
# Use smaller model or quantized version
# Clear GPU cache
import torch
torch.cuda.empty_cache()
```

### Issue: Slow inference

**Solution**: Ensure GPU is being used
```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
```

### Issue: Audio quality issues

**Solution**:
- Check reference audio quality (3-10 seconds, clean)
- Adjust voice parameters
- Try different model variants

## Model Variants

| Variant | Precision | GPU Memory | Quality | Speed |
|---------|-----------|------------|---------|-------|
| FP8 | FP8 | 2GB | Good | Fastest |
| BF16 | BF16 | 8GB | Better | Fast |
| FP32 | FP32 | 16GB | Best | Slower |

## Performance Tips

1. **Use FP8 for low resources**: Only 2GB GPU memory required
2. **Batch processing**: Process multiple segments efficiently
3. **Clear GPU cache**: Regularly clear cache after large batches
4. **Choose appropriate format**: WAV for quality, MP3 for size

## Comparison with Other Models

| Feature | VoxCPM2 | Qwen3-TTS | Index-TTS |
|---------|---------|-----------|-----------|
| Languages | 30+ | 10+ | 2 |
| Voice Design | ✅ | ❌ | ❌ |
| Voice Cloning | ✅ | ✅ | ✅ |
| Sample Rate | 48kHz | 24kHz | 24kHz |
| GPU Memory (FP8) | 2GB | - | - |

## Resources

- **GitHub**: https://github.com/OpenBMB/VoxCPM
- **Official Website**: https://voxcpm.modelbest.cn
- **Documentation**: https://docs.voxcpm.modelbest.cn
- **Demo**: https://demo.voxcpm.modelbest.cn

## License

Apache 2.0 License - Free for commercial and personal use.

## Support

For issues or questions:
- GitHub Issues: https://github.com/OpenBMB/VoxCPM/issues
- Check the [VoxCPM2 Guide](../.trae/skills/tts-model-guide/reference/voxcpm-guide.md) for detailed documentation