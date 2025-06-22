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


def build_openai_tools(tools_list: Optional[List[object]]) -> (List[dict], Dict[str, Callable]):
    """
    Build OpenAI tool schema and a map of tool name to run function from a list of tool objects.
    Args:
        tools_list: List of tool objects, each with a get_definition() method.
    Returns:
        openai_tools: List of OpenAI tool schemas.
        tool_map: Dict mapping tool name to its run function.
    """
    openai_tools = []
    tool_map = {}
    for tool in (tools_list or []):
        try:
            defn = tool.get_definition()
            if not defn:
                continue
            run_fn = defn.pop('run', None)
            name = defn.get('name')
            if run_fn:
                tool_map[name] = run_fn
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
        except Exception as e:
            print(f"[ERROR] Tool registration failed for {tool}: {e}")
    return openai_tools, tool_map


def process_llm_content(msg: object) -> dict:
    """
    Convert an OpenAI message object to a reply dict for the message.reply_with method.
    Handles audio, image, and text blocks.
    """
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
        return out or { 'type': 'text', 'text': '' }
    return { 'type': 'text', 'text': content or '' }


def run_llm_handler(
    bot: Bot,
    message: Message,
    tools_list: Optional[List[object]] = None,
    model_audio: str = "gpt-4o-audio-preview",
    model_default: str = "o4-mini-2025-04-16",
    system_instruction: Optional[str] = None,
    max_function_calls: int = 3,
    as_llm_chat_params: Optional[dict] = None,
    tool_choice: str = "auto",
    debug: bool = False,
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
    multimodal = getattr(message, 'media_type', None) == 'audio'
    model = model_audio if multimodal else model_default
    openai_tools, tool_map = build_openai_tools(tools_list)

    # Prepare chat history
    llm_chat_args = dict(depth=10, mode="thread", system_instruction=system_instruction, multimodal=multimodal)
    if as_llm_chat_params:
        llm_chat_args.update(as_llm_chat_params)
    messages = message.as_llm_chat(**llm_chat_args)
    if debug:
        print("[DEBUG] Initial messages:", messages)
        print("[DEBUG] OpenAI tools:", openai_tools)

    calls_made = 0
    last_msg = None
    file_paths = []  # Accumulate file paths from tool calls
    while calls_made < max_function_calls:
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
        last_msg = msg
        if debug:
            print("[DEBUG] OpenAI response:", msg)
        tool_calls = getattr(msg, 'tool_calls', None)
        if tool_calls:
            if debug:
                print(f"[DEBUG] Detected {len(tool_calls)} tool call(s)")
            tool_responses = []
            for call in tool_calls:
                fname = call.function.name
                fargs = json.loads(call.function.arguments or '{}')
                if debug:
                    print(f"[DEBUG] Executing {fname} with args {fargs}")
                try:
                    result = tool_map[fname](**fargs)
                    # Check if the result is a file path
                    file_path = handle_tool_result(result)
                    if file_path:
                        if debug:
                            print(f"[DEBUG] Tool returned a file: {file_path}")
                        file_paths.append(file_path)
                        # Convert result to string for tool response
                        result = f"File processed: {file_path}"
                    content = json.dumps(result) if not isinstance(result, str) else result
                    tool_responses.append({
                        'role': 'tool',
                        'tool_call_id': call.id,
                        'name': fname,
                        'content': content
                    })
                    if debug:
                        print(f"[DEBUG] {fname} result:", result)
                except Exception as e:
                    if debug:
                        print(f"[ERROR] {fname} failed: {e}")
                    message.reply_with({ 'type': 'text', 'text': f"Error: {e}" })
                    return
            messages.append(msg)
            messages.extend(tool_responses)
            calls_made += 1
            continue
        # No tool calls: finalize
        reply = process_llm_content(msg)
        if debug:
            print("[DEBUG] Sending final reply:", reply)
        # Add any accumulated file paths to the reply
        if file_paths:
            reply.update(prepare_file_response(file_paths, message.platform))
        message.reply_with(reply)
        return
    # Fallback
    content = getattr(last_msg, 'content', '') if last_msg else ''
    fallback = { 'type': 'text', 'text': content or f"Handled by {bot.name}." }
    # Add any accumulated file paths to the fallback reply
    if file_paths:
        fallback.update(prepare_file_response(file_paths, message.platform))
    if debug:
        print("[DEBUG] Fallback reply:", fallback)
    message.reply_with(fallback) 