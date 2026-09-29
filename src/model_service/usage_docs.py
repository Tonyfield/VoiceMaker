"""Template-backed usage markdown rendering for model services.

All per-model data (capabilities, parameters, guidance, examples) comes from
model-profiles.yaml via the profile dict; a single generic template renders
every model.
"""

from __future__ import annotations

from datetime import date
import os
import re
from pathlib import Path
from typing import Any


USAGE_TEMPLATE_DIR = Path(__file__).with_name("usage_templates")
PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

# Shared request-example values for common parameter names. A field's
# "example" attribute in model-profiles.yaml always wins over these.
_FIELD_EXAMPLES: dict[str, str] = {
    "reference_text": "这是参考音频对应原文。",
    "voice_instruction": "用更沉稳、清晰的语气说。",
    "speaker": "Vivian",
    "x_vector_only_mode": "false",
    "tokens": "256",
    "max_new_tokens": "2048",
    "audio_temperature": "1.7",
    "audio_top_p": "0.8",
    "audio_top_k": "25",
    "audio_repetition_penalty": "1.0",
}


def service_base_url() -> str:
    port = str(os.getenv("VOICECLONER_MODEL_SERVICE_PORT", "20200") or "20200").strip()
    return f"http://127.0.0.1:{port}"


def render_model_usage_markdown(
    model_name: str,
    metadata: dict[str, Any],
    profile: dict[str, Any],
) -> str:
    template = _load_template()
    context = _build_template_context(
        model_name=model_name,
        metadata=metadata,
        profile=profile,
        base_url=service_base_url(),
    )
    return PLACEHOLDER_PATTERN.sub(
        lambda match: context.get(match.group(1), match.group(0)),
        template,
    )


def _load_template() -> str:
    template_path = USAGE_TEMPLATE_DIR / "generic.md"
    return template_path.read_text(encoding="utf-8")


def _build_template_context(
    model_name: str,
    metadata: dict[str, Any],
    profile: dict[str, Any],
    base_url: str,
) -> dict[str, str]:
    segmentation = profile.get("segmentation") or {}
    capabilities = profile.get("capabilities") or {}
    fields = _base_parameter_fields(profile)
    description = str(metadata.get("description") or "").strip() or "未提供额外模型描述。"
    notes = str(segmentation.get("notes") or "").strip() or "无额外 profile 说明。"
    token_guidance = "由当前运行时决定。"
    if segmentation.get("target_input_tokens") not in (None, ""):
        token_guidance = (
            f"建议目标输入 token 为 `{segmentation.get('target_input_tokens')}`，"
            f"硬上限为 `{segmentation.get('max_input_tokens')}`。"
        )

    return {
        "MODEL_LABEL": str(profile.get("label") or metadata.get("label") or model_name),
        "MODEL_NAME": model_name,
        "VERSION": str(profile.get("version") or "unknown"),
        "DOC_DATE": date.today().isoformat(),
        "PROFILE_ID": str(segmentation.get("strategy_id") or "generic"),
        "MODEL_DESCRIPTION": description,
        "ABILITY_NOTES": notes,
        "CAPABILITY_TABLE": _capability_table(capabilities),
        "REFERENCE_REQUIRED": _format_bool(bool(profile.get("requires_reference"))),
        "VOICE_INSTRUCTION_SUPPORT": _format_bool(
            bool(profile.get("supports_voice_instruction"))
        ),
        "MIN_REFERENCE_AUDIO_SECONDS": str(profile.get("min_reference_audio_seconds", 0.0)),
        "SUPPORTED_LANGUAGES": _format_languages(profile.get("supported_languages") or []),
        "SEGMENTATION_SUMMARY": (
            f"单段建议 `max_chars_per_segment={segmentation.get('max_chars_per_segment', 'n/a')}`，"
            f"目标时长 `max_estimated_duration_seconds={segmentation.get('max_estimated_duration_seconds', 'n/a')}` 秒。"
        ),
        "TOKEN_GUIDANCE": token_guidance,
        "BASE_URL": base_url,
        "ENDPOINT_TABLE": _endpoint_table(),
        "REQUEST_EXAMPLE": _request_example(model_name, profile, base_url),
        "PYTHON_RESPONSE_EXAMPLE": _python_response_example(
            base_url=base_url,
            requires_reference=bool(profile.get("requires_reference")),
        ),
        "PARAMETER_SUMMARY_TABLE": _parameter_summary_table(fields),
        "PARAMETER_DETAILS": "\n\n".join(_field_detail(field) for field in fields),
    }


def _capability_table(capabilities: dict[str, Any]) -> str:
    """Render the capability matrix declared in model-profiles.yaml."""
    rows: list[tuple[str, bool]] = [
        ("参考音频克隆（voice sample）", bool(capabilities.get("requires_reference"))),
        ("情绪文本控制（emotion text）", bool(capabilities.get("emotion_text"))),
        ("风格/音色自然语言指令（voice instruction）", bool(capabilities.get("voice_instruction"))),
        ("参考音频原文（ICL / continuation）", bool(capabilities.get("reference_text"))),
        ("预设说话人（speaker presets）", bool(capabilities.get("speaker_presets"))),
    ]
    lines = [
        "| 能力 | 支持 |",
        "| --- | --- |",
    ]
    for label, supported in rows:
        lines.append(f"| {label} | {_format_bool(supported)} |")
    return "\n".join(lines)


def _format_bool(value: bool) -> str:
    return "是" if value else "否"


def _format_languages(languages: list[str]) -> str:
    if not languages:
        return "由当前运行时决定"
    return ", ".join(f"`{item}`" for item in languages)


def _format_default(value: Any) -> str:
    if value in (None, ""):
        return "无"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _base_parameter_fields(profile: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = [
        {
            "name": "text",
            "label": "待合成文本",
            "type": "text",
            "required": True,
            "help": "所有模型都需要该字段。",
        },
        {
            "name": "language",
            "label": "语言代码",
            "type": "text",
            "required": False,
            "default": "auto",
            "help": "若模型支持自动识别，优先使用 auto。",
            "placeholder": "auto",
        },
    ]
    if profile.get("requires_reference"):
        fields.append(
            {
                "name": "reference_audio",
                "label": "参考音频文件",
                "type": "file",
                "required": True,
                "help": "通过 multipart/form-data 上传二进制音频文件。",
            }
        )

    existing_names = {field["name"] for field in fields}
    for field in profile.get("task_inputs", []):
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "").strip()
        if not name or name in existing_names:
            continue
        fields.append(dict(field))
        existing_names.add(name)

    return fields


def _endpoint_table() -> str:
    return "\n".join(
        [
            "| 访问点 | 方法 | 用途 |",
            "| --- | --- | --- |",
            "| `/api/health` | `GET` | 查看模型服务健康状态、模型是否已加载、运行时依赖是否可用。 |",
            "| `/api/profile` | `GET` | 查看当前模型 profile，供前端动态渲染任务参数。 |",
            "| `/api/usage` | `GET` | 查看当前模型的 Markdown 使用说明。 |",
            "| `/api/synthesize` | `POST` | 使用 multipart/form-data 发送请求并直接获得 `audio/wav` 二进制结果。 |",
            "| `/api/synthesize/stream` | `POST` | 使用 multipart/form-data 发送请求并通过 HTTP chunked response 获得 `audio/L16` PCM 流。 |",
        ]
    )


def _request_example(model_name: str, profile: dict[str, Any], base_url: str) -> str:
    request_fields = [
        '-F "text=这是一段用于验证模型服务的示例文本。"',
        '-F "language=auto"',
    ]
    if profile.get("requires_reference"):
        request_fields.append('-F "reference_audio=@reference.wav"')

    for field in profile.get("task_inputs", []):
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        value = field.get("example")
        if value in (None, ""):
            value = field.get("default")
        if value in (None, ""):
            value = _FIELD_EXAMPLES.get(name, f"<{name}>")
        if name == "reference_text" and model_name.startswith("moss_tts"):
            value = field.get("example") or "这是参考音频对应的前缀文本。"
        request_fields.append(f'-F "{name}={value}"')

    request_block = " \\\n+  ".join(request_fields)
    return (
        "```bash\n"
        f"curl -X POST \"{base_url}/api/synthesize\" \\\n+  {request_block} \\\n+  -o output.wav\n"
        "```"
    )


def _python_response_example(base_url: str, requires_reference: bool) -> str:
    if requires_reference:
        request_body = (
            "        data={\n"
            "            \"text\": \"这是一段用于验证模型服务的示例文本。\",\n"
            "            \"language\": \"auto\",\n"
            "        },\n"
            "        files={\n"
            "            \"reference_audio\": (\"reference.wav\", audio_file, \"audio/wav\")\n"
            "        },\n"
        )
        open_block = "with open(\"reference.wav\", \"rb\") as audio_file:\n"
        indent = "    "
    else:
        request_body = (
            "    data={\n"
            "        \"text\": \"这是一段用于验证模型服务的示例文本。\",\n"
            "        \"language\": \"auto\",\n"
            "    },\n"
        )
        open_block = ""
        indent = ""

    return (
        "```python\n"
        "from pathlib import Path\n\n"
        "import httpx\n\n"
        f"{open_block}response = httpx.post(\n"
        f"{indent}    \"{base_url}/api/synthesize\",\n"
        f"{request_body}"
        f"{indent}    timeout=600,\n"
        f"{indent})\n"
        f"{indent}response.raise_for_status()\n"
        f"{indent}Path(\"output.wav\").write_bytes(response.content)\n"
        "```"
    )


def _parameter_summary_table(fields: list[dict[str, Any]]) -> str:
    lines = [
        "| 参数 | 类型 | 必填 | 默认值 | 说明 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for field in fields:
        name = str(field.get("name") or "参数")
        field_type = str(field.get("type") or "text")
        required = _format_bool(bool(field.get("required", False)))
        default = _format_default(field.get("default"))
        summary = str(field.get("help") or field.get("label") or "").strip() or "见下方详细说明"
        summary = summary.replace("\n", " ")
        lines.append(
            f"| `{name}` | `{field_type}` | {required} | {default} | {summary} |"
        )
    return "\n".join(lines)


def _parameter_options_markdown(field: dict[str, Any]) -> str:
    options = field.get("options") or []
    if not isinstance(options, list) or not options:
        return ""
    lines = ["- 可选值："]
    for option in options:
        if not isinstance(option, dict):
            continue
        value = str(option.get("value") or "").strip()
        label = str(option.get("label") or value).strip()
        description = str(option.get("description") or "").strip()
        suffix = f"：{description}" if description else ""
        lines.append(f"  - `{value}` ({label}){suffix}")
    return "\n".join(lines)


def _field_detail(field: dict[str, Any]) -> str:
    name = str(field.get("name") or "").strip()
    label = str(field.get("label") or name or "参数").strip()
    help_text = str(field.get("help") or "").strip()
    placeholder = str(field.get("placeholder") or "").strip()
    default = field.get("default")
    required = bool(field.get("required", False))

    guidance = str(field.get("guidance") or "").strip() or (
        f"{label} 会按当前模型 profile 和运行时配置传递给底层模型。"
    )

    lines = [
        f"### `{name}`",
        f"- 标签：{label}",
        f"- 类型：`{field.get('type', 'text')}`",
        f"- 必填：{_format_bool(required)}",
        f"- 默认值：{_format_default(default)}",
        f"- 说明：{guidance}",
    ]
    if help_text:
        lines.append(f"- Profile 提示：{help_text}")
    if placeholder:
        lines.append(f"- 输入示例：{placeholder}")
    options_markdown = _parameter_options_markdown(field)
    if options_markdown:
        lines.append(options_markdown)
    return "\n".join(lines)