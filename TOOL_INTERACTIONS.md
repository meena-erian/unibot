# Interactive tools

Tools may now return a `unicom.interactions.MessageWithButtons`. UniCom persists
it, displays native buttons on WebChat and Telegram, and holds the tool response
until the user chooses an action. No worker remains blocked waiting for a click.

## Requirements

Deploy compatible UniCom and UniBot versions together and run `python manage.py
migrate` to apply UniCom migration `0027_interaction`. Keep `run_worker` running
for normal bot processing and periodic expiry. Interactive tools support WebChat
and Telegram; other transports are rejected.

## Definition-local handlers

```python
from unicom.interactions import Button, Complete, MessageWithButtons

class PickFormat(MessageWithButtons):
    text = 'Choose a report format'
    buttons = (Button('PDF', 'pdf'), Button('CSV', 'csv', 'secondary'))

    def on_action(self, action, context):
        return Complete(
            {'format': action},
            text=f'Selected {action.upper()}',
            presentation={'format': action},
        )

def run():
    return PickFormat(state={'private_tracking_id': 123})

tool_definition = {
    'name': 'pick_format',
    'description': 'Ask the user which report format they prefer.',
    'parameters': {},
    'run': run,
    'interactions': {'PickFormat': PickFormat},
}
```

Put this in `data/definitions/tools/pick_format.py` and enable `pick_format` in
the bot's `bot_tools`. The existing sync command registers it. Handler identifiers
are persisted as `unibot:pick_format:PickFormat`; keep these names available while
interactions are pending. Handler code is resolved from the synchronized tool
record on every click, so no Python objects or closures need to survive restarts.
Use `state` for JSON values required by a later callback, not globals injected
into the initial tool execution.

For a simple choice without a handler, return `MessageWithButtons(text=...,
buttons=[Button(...)])`. It completes with `{'action': selected_action}`.

`on_action(action, context)` returns either:

- `Complete(result, text=..., presentation=..., cancelled=False)`: finish the tool
  and resume the assistant. `result` is for the model; `presentation` is explicitly
  selected browser data. They need not be identical.
- Another registered `MessageWithButtons`: update the same message with another
  step and new buttons, retaining the original expiration deadline. Old buttons
  cannot execute a later step.

Context provides the persisted interaction, clicking account, tool call, and the
original Django user when available. Handlers receive the private state through
`self.state`. Perform domain-specific authorization against the account as usual.

## Custom web presentations

Add a companion `pick_format.presentation.js` beside the Python definition and
set `web_component = 'pick_format.presentation.js'` on the handler class. Configure
`unibot.finders.ToolPresentationFinder` in `STATICFILES_FINDERS` (in addition to Django’s existing finders). Normal static collection publishes only `.presentation.js` files;
Python definitions and private state are not served.

For example, retain the default finders and add:

```python
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'unibot.finders.ToolPresentationFinder',
]
```

The finder reads `UNIBOT_DEFINITIONS_DIR/tools`, defaulting to
`BASE_DIR/data/definitions/tools`. Run `collectstatic` during deployment and
serve the collected files from the same origin as WebChat. Use versioned static
URLs and ensure the WebChat JavaScript and companion module are refreshed on
release; cached older clients may show only the text and native buttons.

The JavaScript module exports a standard Web Component class:

```javascript
export default class FormatCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
  }
  set state(state) {
    const title = document.createElement('h3');
    title.textContent = state.text;
    const summary = document.createElement('p');
    summary.textContent = state.status === 'awaiting_input'
      ? 'Select a format below.'
      : `Selected format: ${state.data.format || 'none'}`;
    this.shadowRoot.replaceChildren(title, summary);
  }
}
```

UniCom registers and mounts the component. `.state` contains:

```javascript
{
  id, callId, toolName, status, revision, text,
  data,          // only explicit presentation data
  component, buttons, expiresAt
}
```

States are `awaiting_input`, `completed`, `cancelled`, `expired`, and `error`.
Use `data` for previews and final visualizations; set the completion's
`presentation` to the data the final view needs. Render with DOM text APIs or
escaped templates, not interpolated untrusted HTML. Modules are trusted deployed
application code and must be same-origin. They may use SVG, icons, charts, shadow
DOM, and the inherited `--unicom-*` theme variables. The host supplies accessible
buttons, busy state, CSRF-protected submission, and visible errors. A custom
component can also emit a bubbling, composed `interaction-action` event with
`detail: {action: 'pdf'}` to activate an existing declared action. It cannot add
new server actions by changing client data.

Implement `disconnectedCallback` to release listeners, timers, and in-flight
work. State may be assigned repeatedly as messages refresh. Preserve your own
component-local state where appropriate. If loading the module fails, UniCom
falls back to the text and standard buttons. Telegram always uses that textual
contract, so provide useful `text` for every step and completion.

The initial card appears after the Python tool returns its interaction object,
while the model's tool response is still pending. It is not a hook that renders
before `run()` returns. Pass selected tool arguments into `presentation` for a
data-driven preview; return final display data through `Complete.presentation`.
The existing component receives the new `.state` when the interaction updates.

## Lifecycle and guarantees

The interaction's private state, public data, identity, buttons, revision, result,
and expiration live in the database. Web history reconstructs the card; guest
interactions transfer with chat history at sign-in. Account ownership and channel
are checked for callbacks. CSRF remains enforced on web submissions.

Clicks lock the interaction's parent request and interaction rows. Duplicate or
concurrent clicks on a completed interaction return the saved state and cannot
roll the dice or create another continuation. Sibling pending tools block the
continuation until all have responded. Exceptions roll back database changes and
leave the interaction available for retry. External side effects cannot be
rolled back by Django: use an outbox or the interaction ID as the external
provider's idempotency key, and keep handlers short.

Interactions default to a one-hour deadline; `expires_in` accepts 1 second through
7 days. The UniBot worker checks for expired interactions approximately every
30 seconds between processing batches. Standalone UniCom integrations can run
`python manage.py expire_interactions` periodically. Expiry resolves the tool
with an error result. Telegram projection is best-effort: provider outages can
leave old buttons visible, but those buttons cannot repeat a completed action.

A custom provider adapter must call
`unibot.interactions.handle_interaction_result(value, persisted_tool_call)` before
its ordinary tool-result handling and skip completion when it returns `True`.
UniBot's standard LLM handler already does this.

This release provides buttons, multi-step button interactions, and custom web
presentations. Typed form submission, file fields, Telegram conversational forms,
and streamed intermediate tool data are extension work; arbitrary browser forms
do not automatically become Telegram forms.
