from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from unibot.models import Bot
import base64
import uuid
import re
import json
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Type, Union
from openai import OpenAI
from unicom.models.message import Message
from .tool_result_handler import handle_tool_result, prepare_file_response


def build_openai_tools(tools_list: Optional[List[object]], bot=None, message=None, openai_client=None, request=None, tool_call=None) -> (List[dict], Dict[str, Callable]):
    """
    Build OpenAI tool schema and a map of tool name to run function from a list of tool objects.
    Args:
        tools_list: List of tool objects, each with a get_definition() method.
        tool_call: Optional ToolCall instance to pass to tool execution context.
    Returns:
        openai_tools: List of OpenAI tool schemas.
        tool_map: Dict mapping tool name to its run function.
    """
    openai_tools = []
    tool_map = {}
    for tool in (tools_list or []):
        defn = tool.get_definition(bot=bot, message=message, openai_client=openai_client, request=request, tool_call=tool_call)
        if not defn:
            print(f"[DEBUG] Tool {tool} skipped: get_definition() returned None or empty.")
            continue
        run_fn = defn.pop('run', None)
        name = defn.get('name')
        if not name:
            print(f"[DEBUG] Tool {tool} skipped: definition missing 'name'. Definition: {defn}")
            continue
        if run_fn:
            tool_map[name] = run_fn
        else:
            print(f"[DEBUG] Tool {tool} ('{name}') skipped: definition missing 'run' function. Definition: {defn}")
            continue
        # Build JSON Schema for parameters
        raw_params = defn.get('parameters', {})
        props = {}
        required = []
        for pname, pinfo in raw_params.items():
            ptype = pinfo.get('type', 'string')
            if ptype in ('str', 'string'):
                otype = 'string'
            elif ptype in ('int', 'integer'):
                otype = 'integer'
            elif ptype in ('float', 'number'):
                otype = 'number'
            elif ptype in ('bool', 'boolean'):
                otype = 'boolean'
            else:
                otype = 'string'
            prop = {'type': otype}
            if 'description' in pinfo:
                prop['description'] = pinfo['description']
            if 'default' in pinfo:
                prop['default'] = pinfo['default']
            else:
                required.append(pname)
            props[pname] = prop
        param_schema = { 'type': 'object',
                            'properties': props,
                            'additionalProperties': False }
        if required:
            param_schema['required'] = required
        openai_tools.append({
            'type': 'function',
            'function': {
                'name': name,
                'description': defn.get('description', ''),
                'parameters': param_schema
            },
            'strict': True
        })

    return openai_tools, tool_map


def process_llm_content(msg: object) -> dict:
    """
    Convert an OpenAI message object to a reply dict for the message.reply_with method.
    Handles audio, image, and text blocks.
    """
    # First, handle new-style audio responses returned in msg.audio (OpenAI SDK 1.14+)
    if hasattr(msg, 'audio') and msg.audio and hasattr(msg.audio, 'data'):
        audio_data = msg.audio.data
        transcript = getattr(msg.audio, 'transcript', '')
        audio_id = getattr(msg.audio, 'id', None)
        # Default to opus/ogg if format not provided
        # OpenAI SDK may expose 'format' in msg.audio, but fallback to opus
        audio_format = getattr(msg.audio, 'format', 'opus') or 'opus'
        ext = 'ogg' if audio_format in {'opus', 'ogg'} else audio_format
        audio_file_name = f"media/{uuid.uuid4()}.{ext}"
        with open(audio_file_name, "wb") as f:
            f.write(base64.b64decode(audio_data))
        reply_dict = {
            'type': 'audio',
            'file_path': audio_file_name,
        }
        if audio_id:
            reply_dict['audio_id'] = audio_id
        if transcript:
            reply_dict['text'] = transcript
        return reply_dict

    content = getattr(msg, 'content', None)
    if isinstance(content, list):
        out = None
        for block in content:
            t = block.get('type')
            if t == 'input_audio':
                data = block['input_audio']['data']
                ext = block['input_audio'].get('format','wav')
                path = f"media/{uuid.uuid4()}.{ext}"
                with open(path,'wb') as f:
                    f.write(base64.b64decode(data))
                out = { 'type': 'audio', 'file_path': path, 'text': '' }
            elif t == 'image_url':
                m = re.match(r"data:(.*?);base64,(.*)", block['image_url']['url'])
                if m:
                    ext = m.group(1).split('/')[-1]
                    path = f"media/{uuid.uuid4()}.{ext}"
                    with open(path,'wb') as f:
                        f.write(base64.b64decode(m.group(2)))
                    out = { 'type': 'image', 'file_path': path, 'text': '' }
            elif t == 'text' and out is None:
                out = { 'type': 'text', 'text': block['text'] }
        # Ensure text messages are never empty to avoid Telegram API 400 error
        result = out or { 'type': 'text', 'text': '' }
        if result['type'] == 'text' and not result['text']:
            result['text'] = ' '
        return result
    return { 'type': 'text', 'text': content or '' }


def run_llm_handler(
    bot: Bot,
    message: Message,
    tools_list: Optional[List[object]] = None,
    model_audio: str = "gpt-4o-audio-preview",
    model_default: str = "o4-mini-2025-04-16",
    system_instruction: Optional[str] = None,
    max_function_calls: int = 7,
    as_llm_chat_params: Optional[dict] = None,
    tool_choice: str = "auto",
    debug: bool = False,
    request=None,
    openai_client: OpenAI = None,
) -> None:
    """
    Modular LLM handler for bots supporting audio, text, images, and tool use.
    Args:
        message: The input message object (Message).
        openai_client: The OpenAI client instance.
        tools_list: List of tool objects (optional).
        model_audio: Model name for audio messages.
        model_default: Model name for text messages.
        system_instruction: System/developer prompt (optional).
        max_function_calls: Max number of tool call loops.
        as_llm_chat_params: Dict of params for as_llm_chat (depth, mode, etc.).
        tool_choice: OpenAI tool_choice parameter (default 'auto').
        debug: Print debug info if True.
    Returns:
        None (calls message.reply_with with the reply dict).
    """
    # First get chat history with multimodal=True to check for audio messages
    llm_chat_args = dict(depth=129, mode="thread", system_instruction=system_instruction, multimodal=True)
    if as_llm_chat_params:
        llm_chat_args.update(as_llm_chat_params)
    messages = message.as_llm_chat(**llm_chat_args)

    # Check if any user messages in the conversation are audio
    multimodal = False
    for msg in messages:
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for content_block in msg["content"]:
                if content_block.get("type") == "input_audio":
                    multimodal = True
                    break
            if multimodal:
                break

    model = model_audio if multimodal else model_default
    print(f"[DEBUG] tools_list: {tools_list}")
    print(f"[DEBUG] multimodal detected: {multimodal}, using model: {model}")
    # Note: tool_call will be set per-tool during execution, passing None here for initial schema building
    openai_tools, tool_map = build_openai_tools(tools_list, bot=bot, message=message, openai_client=openai_client, request=request, tool_call=None)
    if debug:
        print("[DEBUG] Initial messages:", messages)
        print("[DEBUG] OpenAI tools:", openai_tools)

    # Single LLM call instead of loop - unicom handles tool call coordination
    kwargs = {}
    if multimodal:
        kwargs.update({ 'modalities': ['text','audio'],
                        'audio': { 'voice': 'alloy', 'format': 'opus' } })
    if openai_tools:
        kwargs.update({ 'tools': openai_tools, 'tool_choice': tool_choice })
    if debug:
        print(f"[DEBUG] Calling OpenAI: model={model}, kwargs={kwargs}")
    resp = openai_client.chat.completions.create(
        model=model,
        messages=messages,
        **kwargs
    )
    msg = resp.choices[0].message
    if debug:
        print("[DEBUG] OpenAI response:", msg)

    tool_calls = getattr(msg, 'tool_calls', None)
    if tool_calls:
        if debug:
            print(f"[DEBUG] Detected {len(tool_calls)} tool call(s)")

        # Convert OpenAI tool calls to unicom format
        tool_call_data = []
        for call in tool_calls:
            fname = call.function.name
            fargs = json.loads(call.function.arguments or '{}')
            tool_call_data.append({
                "name": fname,
                "arguments": fargs,
                "id": call.id  # Use OpenAI's call ID
            })

        # Submit all tool calls to unicom (atomic operation)
        unicom_tool_calls = request.submit_tool_calls(tool_call_data)

        # Execute each tool and respond immediately unless the tool returns None (which means the tool handles its own response asynchronously)
        file_paths = []  # Accumulate file paths from tool calls
        for i, call in enumerate(tool_calls):
            fname = call.function.name
            fargs = json.loads(call.function.arguments or '{}')
            tool_call_instance = unicom_tool_calls[i]

            if debug:
                print(f"[DEBUG] Executing {fname} with args {fargs}")

            # Rebuild tool map with tool_call context for this specific tool
            _, tool_map_with_context = build_openai_tools(
                tools_list,
                bot=bot,
                message=message,
                openai_client=openai_client,
                request=request,
                tool_call=tool_call_instance
            )

            # Execute tool with tool_call in context
            result = tool_map_with_context[fname](**fargs)

            # If tool returns None, it handles its own response - mark as ACTIVE
            if result is None:
                tool_call_instance.mark_active()
                if debug:
                    print(f"[DEBUG] {fname} returned None - tool is now ACTIVE and waiting for async response")
                continue

            # Handle file results (existing code)
            file_path = handle_tool_result(result)
            if file_path:
                if debug:
                    print(f"[DEBUG] Tool returned a file: {file_path}")
                file_paths.append(file_path)
                result = f"File processed: {file_path}"

            # Respond to unicom tool call automatically
            tool_call_instance.respond(result)

            if debug:
                print(f"[DEBUG] {fname} result:", result)

        # Child request will be automatically created by unicom when all tool calls are responded to
        return

    # No tool calls: send final response
    reply = process_llm_content(msg)

    # If reply is text but the text is empty/whitespace, remove text key and
    # attempt to infer a better type from any attached file_path.
    if reply.get('type') == 'text' and (not reply.get('text') or not str(reply['text']).strip()):
        reply.pop('text', None)
        fpath = reply.get('file_path')
        if fpath:
            # If multiple paths, take first for type inference
            if isinstance(fpath, list):
                fpath = fpath[0]
            ext = Path(fpath).suffix.lower()
            if ext in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}:
                reply['type'] = 'image'
            elif ext in {'.mp3', '.wav', '.opus', '.ogg', '.m4a'}:
                reply['type'] = 'audio'
            else:
                reply['type'] = 'file'
        else:
            # Nothing to send; fallback to a minimal placeholder to avoid empty text error
            reply['text'] = '...'  # will be treated as short text

    if debug:
        print("[DEBUG] Sending final reply:", reply)
    message.reply_with(reply)
