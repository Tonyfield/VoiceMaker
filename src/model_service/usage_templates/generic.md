# {{MODEL_LABEL}} usage

这份文档由 `model-profiles.yaml` 中的 profile 数据自动生成。访问
`/api/usage` 可查看最新内容；修改 profile 或本模板即可调整展示，
无需改动 Python 代码。

## 模型描述

- 模型描述：{{MODEL_DESCRIPTION}}
- 版本：`{{VERSION}}`
- 日期：`{{DOC_DATE}}`
- profile：`{{PROFILE_ID}}`
- 最短参考音频：`{{MIN_REFERENCE_AUDIO_SECONDS}}` 秒
- 支持语言：{{SUPPORTED_LANGUAGES}}
- 分段建议：{{SEGMENTATION_SUMMARY}}
- Token 建议：{{TOKEN_GUIDANCE}}
- 能力补充：{{ABILITY_NOTES}}

## 模型能力矩阵

下表列出该模型 API 实际接受的输入能力。不同模型能力不同：有的接受
voice sample（参考音频克隆），有的接受 emotion text（情绪文本），有的
只接受自然语言风格指令。

{{CAPABILITY_TABLE}}

## 建议使用场景

- 通用文本转语音服务化调用。
- 需要通过 `/api/profile` 动态读取参数并由客户端自动渲染的场景。
- 希望将模型服务说明与运行时代码分离管理的部署方式。

## tts 服务使用指南

你可以使用下面这些访问点与当前模型服务交互。

{{ENDPOINT_TABLE}}

当前服务基础地址是 `{{BASE_URL}}`。`POST /api/synthesize` 使用
`multipart/form-data`，成功时直接返回 `audio/wav` 二进制数据。若模型支持流式，
还可以调用 `/api/synthesize/stream` 获得 `audio/L16` PCM chunk 流，并从响应头
`X-Audio-Sample-Rate`、`X-Audio-Format`、`X-Audio-Channels` 读取音频元数据。

### 请求访问方式

{{REQUEST_EXAMPLE}}

### 返回数据格式和读取方式

- 成功时返回 `HTTP 200`，响应体为 `audio/wav`。
- 流式接口成功时返回 `HTTP 200`，响应体为 `audio/L16` PCM 字节流。
- 失败时返回 JSON，通常包含 `detail` 字段。
- 命令行调用建议用 `-o output.wav` 直接保存响应体。
- 程序调用时直接读取二进制内容并写入 WAV 文件。

{{PYTHON_RESPONSE_EXAMPLE}}

## 请求参数速览

下面这张表汇总当前模型服务会实际使用的请求参数。

{{PARAMETER_SUMMARY_TABLE}}

## 请求参数详细说明

下面给出逐项参数说明。若你只想改展示文案，可以直接编辑当前模板文件。

{{PARAMETER_DETAILS}}
