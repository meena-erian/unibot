import base64
import uuid
import re
import json

def handle_incoming_message(message, bot, tools_list, max_function_calls=3):
    """
    Simplified handler without LlamaIndex.
    Handles incoming messages, passes tool definitions directly to OpenAI,
    and executes any function calls returned.
    """
    global openai_client

    # Choose model
    model = ("gpt-4o-audio-preview" 
             if getattr(message, 'media_type', None) == 'audio' 
             else "o4-mini-2025-04-16")
    multimodal = getattr(message, 'media_type', None) == 'audio'

    # Prepare OpenAI tools and map of run functions
    openai_tools = []
    tool_map = {}
    print("[DEBUG] Received tools_list:", tools_list)

    for tool in (tools_list or []):
        try:
            defn = tool.get_definition()
            if not defn:
                continue
            run_fn = defn.pop('run', None)
            name = defn.get('name')
            # Store run function
            if run_fn:
                tool_map[name] = run_fn

            # Build proper JSON Schema for parameters
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
            print(f"[DEBUG] Registered tool: {name}")
        except Exception as e:
            print(f"[ERROR] Tool registration failed for {tool}: {e}")

    print("[DEBUG] OpenAI tools payload:", openai_tools)

    # Build chat history without system summary
    if hasattr(message, 'as_llm_chat'):
        messages = message.as_llm_chat(
            depth=10,
            mode="thread",
            system_instruction=None,
            multimodal=multimodal
        )
    else:
        messages = [{ 'role': 'user', 'content': message.text }]

    print("[DEBUG] Initial messages:", messages)

    calls_made = 0
    last_msg = None

    while calls_made < max_function_calls:
        kwargs = {}
        if multimodal:
            kwargs.update({ 'modalities': ['text','audio'],
                            'audio': { 'voice': 'alloy', 'format': 'opus' } })
        if openai_tools:
            kwargs.update({ 'tools': openai_tools, 'tool_choice': 'auto' })

        print(f"[DEBUG] Calling OpenAI: model={model}, kwargs={kwargs}")
        resp = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
        msg = resp.choices[0].message
        last_msg = msg
        print("[DEBUG] OpenAI response:", msg)

        tool_calls = getattr(msg, 'tool_calls', None)
        if tool_calls:
            print(f"[DEBUG] Detected {len(tool_calls)} tool call(s)")
            tool_responses = []
            for call in tool_calls:
                fname = call.function.name
                fargs = json.loads(call.function.arguments or '{}')
                print(f"[DEBUG] Executing {fname} with args {fargs}")
                try:
                    result = tool_map[fname](**fargs)
                    content = json.dumps(result) if not isinstance(result, str) else result
                    tool_responses.append({
                        'role': 'tool',
                        'tool_call_id': call.id,
                        'name': fname,
                        'content': content
                    })
                    print(f"[DEBUG] {fname} result:", result)
                except Exception as e:
                    print(f"[ERROR] {fname} failed: {e}")
                    message.reply_with({ 'type': 'text', 'text': f"Error: {e}" })
                    return
            messages.append(msg)
            messages.extend(tool_responses)
            calls_made += 1
            continue

        # No tool calls: finalize
        reply = _process_llm_content(msg)
        print("[DEBUG] Sending final reply:", reply)
        message.reply_with(reply)
        return

    # Fallback
    content = getattr(last_msg, 'content', '') if last_msg else ''
    fallback = { 'type': 'text', 'text': content or f"Handled by {bot.name}." }
    print("[DEBUG] Fallback reply:", fallback)
    message.reply_with(fallback)


def _process_llm_content(msg):
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