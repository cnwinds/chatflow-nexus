# 百炼 TTS 服务开发文档

## 概述

百炼 TTS 服务是基于阿里云百炼平台的文本转语音服务，提供统一的 TTS 调用接口。支持 CosyVoice 模型和 SSML 标记语言。

## 功能特性

- ✅ 文本转语音合成
- ✅ SSML 标记语言支持
- ✅ 流式音频生成
- ✅ 多语音选择
- ✅ 统计信息收集
- ✅ 错误处理和日志记录

## 配置说明

### 基本配置

在 `default_config.json` 中配置以下参数：

```json
{
  "service_config": {
    "default_voice": "zh-CN-XiaoyiNeural",  // 默认语音
    "default_language": "zh-CN",           // 默认语言
    "sample_rate": 16000,                   // 采样率
    "audio_format": "wav",                  // 音频格式
    "enable_ssml": true,                    // 启用SSML支持
    "max_text_length": 5000,                // 最大文本长度
    "timeout": 30                           // 超时时间（秒）
  },
  "bailian_config": {
    "api_key": "",                          // 百炼平台API密钥（必需）
    "base_url": "",                         // API基础URL（可选，自动根据region设置）
    "region": "cn-beijing"                  // 地域：cn-beijing 或 ap-singapore
  },
  "voice_config": {
    "model_name": "cosyvoice-1.5",          // 模型名称
    "available_voices": {                   // 可用语音列表
      "zh-CN": [...],
      "en-US": [...]
    }
  }
}
```

### 必需配置项

- `bailian_config.api_key`: 百炼平台的 API 密钥，必需配置

### 可选配置项

- `bailian_config.base_url`: API 基础 URL，如果不配置会根据 region 自动设置
- `bailian_config.region`: 地域，支持 `cn-beijing`（默认）和 `ap-singapore`

## API 文档

### 官方文档链接

- 百炼控制台文档: https://bailian.console.aliyun.com/?tab=doc#/doc/?type=model&url=2842586
- CosyVoice SSML 标记语言介绍: https://help.aliyun.com/zh/model-studio/introduction-to-cosyvoice-ssml-markup-language

## 工具列表

### 1. synthesize_speech

将文本转换为语音。

**参数：**
- `text` (string, 必需): 要转换的文本内容，支持 SSML 格式
- `voice` (string, 可选): 语音名称
- `ssml` (boolean, 可选): 是否使用 SSML 格式，默认 false
- `voice_params` (object, 可选): 语音参数，支持 rate（语速）、pitch（音高）、range（音高范围）、volume（音量）、contour（音高轮廓）

**注意：** `voice_params` 参数会生成 SSML 的 `<prosody>` 标签。如果百炼平台不支持 prosody 标签，这些参数可能会被忽略或导致错误。建议先测试确认平台是否支持。

**返回：**
```json
{
  "success": true,
  "audio_data": "<base64编码的音频数据>",
  "audio_size": 12345,
  "text_length": 100,
  "voice": "zh-CN-XiaoyiNeural",
  "audio_duration": 4.5,
  "execution_time": 1.2,
  "audio_format": "wav",
  "sample_rate": 16000
}
```

### 2. synthesize_speech_stream

流式将文本转换为语音，实时返回音频块。

**参数：**
- `text` (string, 必需): 要转换的文本内容，支持 SSML 格式
- `voice` (string, 可选): 语音名称
- `ssml` (boolean, 可选): 是否使用 SSML 格式，默认 false
- `voice_params` (object, 可选): 语音参数，支持 rate（语速）、pitch（音高）、range（音高范围）、volume（音量）、contour（音高轮廓）

**注意：** `voice_params` 参数会生成 SSML 的 `<prosody>` 标签。如果百炼平台不支持 prosody 标签，这些参数可能会被忽略或导致错误。建议先测试确认平台是否支持。

**返回：**
流式返回音频块和元数据。

### 3. get_available_voices

获取可用的语音列表。

**参数：**
- `language` (string, 可选): 语言代码（zh-CN 或 en-US）

**返回：**
```json
{
  "success": true,
  "voices": ["zh-CN-XiaoyiNeural", ...],
  "language": "zh-CN",
  "total_count": 18
}
```

### 4. get_service_status

获取服务状态和统计信息。

**返回：**
```json
{
  "success": true,
  "service_name": "bailian_tts_service",
  "status": "running",
  "stats": {
    "total_requests": 100,
    "successful_requests": 95,
    "failed_requests": 5,
    "total_characters": 5000,
    "total_audio_duration": 200.5
  },
  "config": {
    "default_voice": "zh-CN-XiaoyiNeural",
    "default_language": "zh-CN",
    "sample_rate": 16000,
    "audio_format": "wav",
    "enable_ssml": true,
    "max_text_length": 5000,
    "timeout": 30,
    "model_name": "cosyvoice-1.5",
    "log_level": "INFO"
  }
}
```

## SSML 支持

百炼 TTS 服务支持 CosyVoice SSML 标记语言，可以精细控制语音合成的各个方面。

### SSML 格式示例

```xml
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN">
  <voice name="zh-CN-XiaoyiNeural">
    你好，这是一段测试文本。
  </voice>
</speak>
```

### 使用 SSML

在调用 `synthesize_speech` 或 `synthesize_speech_stream` 时，设置 `ssml=true` 参数即可使用 SSML 格式。

## Voice Params 支持

服务支持 `voice_params` 参数来精细控制语音合成的各个方面，包括语速、音高、音量等。这些参数会转换为 SSML 的 `<prosody>` 标签。

### 支持的参数

- **rate**（语速）
  - 相对倍数：`"0.5"`（减半）、`"1"`（默认）、`"2"`（加倍）
  - 百分比：`"50%"`, `"-30%"`
  - 枚举：`"x-slow" | "slow" | "medium" | "fast" | "x-fast"`
  - 建议范围：0.5～2（±100% 以内更自然）

- **pitch**（基准音高）
  - 绝对值：`"600Hz"`
  - 相对值：`"+80Hz"`, `"-2st"`
  - 百分比：`"50%"`, `"-50%"`
  - 枚举：`"x-low" | "low" | "medium" | "high" | "x-high"`
  - 建议范围：原音高的 0.5～1.5 倍

- **range**（音高变化范围）
  - 表达方式与 pitch 相同（绝对/相对/百分比/枚举）

- **volume**（音量）
  - 绝对值（0～1 或 0～100）：`"0.6"` 或 `"60"`
  - 相对量：`"+10"`, `"-5.5"`
  - 百分比：`"50%"`, `"+3%"`
  - 枚举：`"silent" | "x-soft" | "soft" | "medium" | "loud" | "x-loud"`

- **contour**（音高轮廓）
  - 格式：`"(0%,+20Hz) (10%,-2st) (40%,+10Hz)"`
  - 作用：按文本时长百分比指定音高变化轨迹
  - 建议：不要用于很短的词/短语

### 使用示例

```python
# 调整语速和音量
voice_params = {
    "rate": "1.2",
    "volume": "medium"
}

result = await service.synthesize_speech(
    text="这是一段测试文本",
    voice_params=voice_params,
    use_ssml=True
)

# 温柔低沉风格
voice_params = {
    "pitch": "low",
    "range": "x-low",
    "rate": "0.85",
    "volume": "soft"
}

result = await service.synthesize_speech(
    text="这是一段温柔的文本",
    voice_params=voice_params,
    use_ssml=True
)
```

### 注意事项

⚠️ **重要提示**：`voice_params` 功能依赖于百炼平台是否支持 SSML 的 `<prosody>` 标签。如果平台不支持，这些参数可能会被忽略或导致错误。建议：

1. 先测试简单的 `voice_params`（如只设置 `rate`）
2. 查看平台文档确认是否支持 prosody 标签
3. 如果平台不支持，可以忽略 `voice_params` 参数，服务仍可正常工作

## 使用示例

### Python 代码示例

```python
from src.services.bailian_tts_service import BailianTTSService

# 创建服务实例（通常由UTCP框架管理）
service = BailianTTSService(config, config_manager, logger)

# 初始化服务
service.init()

# 合成语音（基础用法）
result = await service.synthesize_speech(
    text="你好，这是测试文本",
    voice="zh-CN-XiaoyiNeural",
    use_ssml=False
)

if result and result.get("success"):
    audio_data = result["audio_data"]
    # 处理音频数据
    print(f"音频大小: {result['audio_size']} 字节")
    print(f"音频时长: {result['audio_duration']} 秒")

# 使用voice_params调整语音参数
voice_params = {
    "rate": "1.2",      # 加快语速
    "pitch": "+2st",    # 提高音高
    "volume": "medium"  # 中等音量
}

result = await service.synthesize_speech(
    text="这是一段调整了参数的文本",
    voice="zh-CN-XiaoyiNeural",
    use_ssml=True,      # 必须启用SSML才能使用voice_params
    voice_params=voice_params
)
```

### 流式合成示例

```python
# 流式合成
async for chunk in service.synthesize_speech_stream(
    text="这是一段较长的文本...",
    voice="zh-CN-XiaoyiNeural"
):
    if chunk.get("type") == "audio_chunk":
        # 处理音频块
        audio_chunk = chunk["audio_chunk"]
        print(f"收到音频块 {chunk['chunk_index']}, 大小: {len(audio_chunk)}")
    elif chunk.get("type") == "metadata":
        # 处理元数据
        print(f"合成完成，总大小: {chunk['audio_size']}")
```

## 错误处理

服务使用统一的错误处理机制，所有错误都会返回标准格式：

```json
{
  "success": false,
  "error": "错误描述",
  "audio_data": "",
  "audio_size": 0
}
```

常见错误：
- API 密钥未配置
- 文本长度超过限制
- API 调用失败
- 网络超时

## 依赖项

- `dashscope`: 阿里云百炼平台官方SDK，用于调用TTS API
- `asyncio`: 异步支持
- `concurrent.futures`: 线程池支持（用于异步执行同步SDK调用）

安装依赖：
```bash
pip install dashscope
```

## 注意事项

1. **API 密钥安全**: 请妥善保管 API 密钥，不要提交到代码仓库
2. **文本长度限制**: 默认最大文本长度为 5000 字符，超过会被截断
3. **超时设置**: 默认超时时间为 30 秒，可根据网络情况调整
4. **流式支持**: 当前实现将完整音频分块返回，并非真正的流式 API
5. **SSML 格式**: 使用 SSML 时需要确保文本符合 CosyVoice SSML 规范

## 开发指南

### 添加新功能

1. 在 `service.py` 中添加新的方法
2. 在 `get_tools()` 中注册新工具
3. 在 `call_tool()` 中添加工具处理逻辑
4. 更新 `default_config.json` 添加相关配置
5. 更新本文档

### 测试

建议编写单元测试和集成测试来验证功能：

```python
import pytest
from src.services.bailian_tts_service import BailianTTSService

@pytest.mark.asyncio
async def test_synthesize_speech():
    # 测试代码
    pass
```

## 更新日志

### v1.0.0 (2024-11-07)
- 初始版本
- 支持基本的文本转语音功能
- 支持 SSML 格式
- 支持流式音频生成
- 支持多语音选择

## 相关链接

- [百炼平台控制台](https://bailian.console.aliyun.com/)
- [CosyVoice SSML 文档](https://help.aliyun.com/zh/model-studio/introduction-to-cosyvoice-ssml-markup-language)
- [UTCP 框架文档](../utcp/README.md)

