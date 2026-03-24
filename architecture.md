# OS2I Architecture — Structured Agent on Small LLMs

## 1. Vision

Most agent frameworks assume a large model that can plan, reason, and act in a
single context window. OS2I takes the opposite approach — break the agent loop
into small, focused steps, each handled by a separate LLM call or a deterministic
executor. Any model that can solve one focused problem at a time can run this
system.

The result is a structured ReAct loop where:

- **Thought** is externalised as an Abstract DSTT (a plan)
- **Action** is compiled into a grounded tool call by a small LLM
- **Observation** is executed deterministically and merged into state
- **State** is the only memory — explicit, inspectable, passed between services

No single model sees the whole task. Each service sees exactly what it needs.


## 2. System Overview

```
User / Caller
     │
     ▼
┌─────────────┐     abstract_dstt      ┌──────────────────┐
│  task2plan  │ ─────────────────────► │  taskexecutor    │
│             │                        │                  │
│  task →     │                        │  for each        │
│  abstract   │                        │  transition:     │
│  DSTT       │                        │                  │
└─────────────┘                        │  ┌────────────┐  │
                                       │  │transition  │  │
                                       │  │2exec       │  │
                                       │  │            │  │
                                       │  │abstract →  │  │
                                       │  │executable  │  │
                                       │  └────────────┘  │
                                       │       │          │
                                       │  dispatch tool   │
                                       │       │          │
                                       │  state.update    │
                                       └──────────────────┘
                                                │
                                                ▼
                                          final state
                                          execution log
```

### Services

| Service          | Port | Responsibility                                      |
|------------------|------|-----------------------------------------------------|
| task2plan        | 8000 | Task → Abstract DSTT (LLM)                          |
| transition2exec  | 8001 | Abstract transition → Executable transition (LLM)   |
| taskexecutor     | 8002 | Execute DSTT, manage state, dispatch tools          |

### Data flow

```
task + context
    → task2plan
    → abstract_dstt

abstract_dstt + state
    → taskexecutor
    → for each abstract_transition:
          abstract_transition + state → transition2exec → executable_transition
          executable_transition.inputs → state (patch)
          tool(state) → outputs → state (merge)
    → completed state + execution log
```


## 3. Core Concepts

### Abstract DSTT
A plan expressed as abstract tool names and key names — no concrete values,
no grounded tool calls. Produced by task2plan. Describes *what* to do.

```json
{
  "segments": [{
    "transitions": [{
      "id": "t1",
      "tool": "check_python_file_existence",
      "inputs": ["project_folder_path"],
      "outputs": ["python_file_exists"]
    }],
    "milestone": ["python_file_exists"]
  }]
}
```

### Executable DSTT
A grounded plan with concrete tool names, concrete input values, and null
output slots. Produced by transition2exec. Describes *how* to do it.

```json
{
  "status": "ok",
  "segments": [{
    "transitions": [{
      "id": "t1",
      "tool": "exists",
      "inputs": {"file_path": "/path/to/hello.py"},
      "outputs": {"is_present": null}
    }],
    "milestone": ["is_present"]
  }]
}
```

### State
A flat key-value dict — the single source of truth for all inputs and outputs.

- Initialised from the caller's context (runtime facts)
- transition2exec contributes resolved concrete values (inputs patch)
- Tools read from state and write back to state
- Grows cumulatively — nothing is removed during execution
- Passed as `context` to transition2exec on every call

### Segment / Transition / Milestone
- **Transition** — one unit of work: one abstract tool → one or more grounded tools
- **Segment** — a group of transitions that together achieve a milestone
- **Milestone** — the set of output keys that must be in state before the next
  segment begins. Acts as a checkpoint gate.

### Tool Registry
Tools are injected into the taskexecutor kernel at startup. The kernel dispatches
by name only — it has no knowledge of what any tool does. This is the primary
extension point for adding new capabilities.

### Subtask
A tool in the registry that spawns a new kernel instance for a sub-problem.
Takes `task`, `context`, and `parent_task` as inputs. Before executing, it checks
that the subtask is a genuine reduction of the parent (LLM binary check). If not,
it fails immediately. The parent kernel blocks until the subtask completes.


## 4. Service Contracts

### task2plan
```
POST /task2plan
{
  "task": "string"
}

→ {
  "abstract_dstt": { segments: [...] },
  "meta": { "status": "ok|ambiguous|low_confidence", ... }
}
```

### transition2exec
```
POST /transition2exec
{
  "task": "string",
  "context": { ...state... },
  "abstract_transition": { id, tool, inputs, outputs, ... },
  "available_tools": [ ...grounded tool catalog... ]  // optional
}

→ {
  "executable_dstt": { status, segments: [...] },
  "meta": { "status": "ok|error", "model": "...", ... }
}
```

### taskexecutor
```
POST /taskexec
{
  "task": "string",
  "parent_task": null,          // null for top-level, set for subtask calls
  "state": { ...context... },
  "abstract_dstt": { segments: [...] }
}

→ {
  "status": "completed|failed",
  "state": { ...final state... },
  "execution_log": [
    { "transition_id", "tool", "inputs", "outputs", "status", "error" }
  ],
  "segments_completed": 1,
  "milestone_reached": ["key1", "key2"]
}
```


## 5. Execution Flow

End-to-end trace for: *"Check whether hello.py exists in the project folder."*

```
1. Caller → POST /task2plan
   { "task": "Check whether hello.py exists in the project folder." }

   ← abstract_dstt:
     segment[0] → t1: check_python_file_existence
                  inputs: [project_folder_path]
                  outputs: [python_file_exists]

2. Caller → POST /taskexec
   {
     "task": "Check whether hello.py exists...",
     "state": { "project_folder_path": "/path/project", "target_file": "hello.py" },
     "abstract_dstt": { ...from step 1... }
   }

3. taskexecutor kernel → POST /transition2exec
   {
     "task": "Check whether hello.py exists...",
     "context": { "project_folder_path": "/path/project", "target_file": "hello.py" },
     "abstract_transition": { "tool": "check_python_file_existence", ... }
   }

   ← executable_dstt:
     t1: exists  inputs: { "file_path": "/path/project/hello.py" }
                 outputs: { "is_present": null }

4. kernel patches state:
   state["file_path"] = "/path/project/hello.py"

5. kernel dispatches: exists(state)
   → reads state["file_path"]
   → Path("/path/project/hello.py").exists() → True
   → returns { "is_present": True }

6. kernel merges:
   state["is_present"] = True

7. milestone ["python_file_exists"] resolved via "is_present" in state → reached

8. ← taskexec response:
   {
     "status": "completed",
     "state": { ..., "is_present": true },
     "execution_log": [{ "tool": "exists", "outputs": {"is_present": true}, "status": "ok" }],
     "milestone_reached": ["is_present"]
   }
```


## 6. Design Principles

**One LLM call per step, small and focused**
Each LLM call solves one narrow problem: map one abstract tool to one grounded
tool. The model never sees the full task history, only the current transition
and the current state.

**Hard failures, no silent fallbacks**
If a transition cannot be mapped or a tool fails, execution stops immediately.
The caller sees the exact failure point and the state at that point. Nothing
is swallowed silently.

**State over context window**
State is the agent's memory. It is explicit, serialisable, and passed between
services as a plain dict. No model holds memory between calls.

**DSTT as working memory**
The abstract DSTT is the plan. The executable DSTT is the compiled plan. Both
are data — inspectable, loggable, replayable.

**Tools are the extension point**
The kernel has no built-in capabilities. Everything it can do comes from the
tool registry. Adding a new capability means adding a tool — no kernel changes.

**Subtask = recursive agent, not special case**
A subtask is just another tool. The kernel does not know it spawns a new agent.
The reduction check (is this task scoped inside the parent?) prevents infinite
loops without a depth counter.


## 7. What This Is Not

- **Not a full agent framework** — no memory management, no prompt chaining,
  no agent personas. One loop, one state bag.
- **Not multi-model orchestration** — all LLM calls use the same model config.
  Different models per service are possible but not the design goal.
- **Not parallel** — execution is strictly sequential within a segment.
  Segments are also sequential.
- **Not LangChain / AutoGen / CrewAI** — no agent abstractions, no prompt
  templates beyond the two in `prompts/`. Just FastAPI, Pydantic, DSPy, and
  stdlib.


## 8. Reference Implementation

The reference implementation lives in this repository under `src/`.

### Stack

| Concern         | Library              | Why                                      |
|-----------------|----------------------|------------------------------------------|
| HTTP service    | FastAPI              | Lightweight, Pydantic-native             |
| Data models     | Pydantic v2          | Validation, serialisation, no boilerplate|
| LLM calls       | DSPy + Ollama        | Local model support, simple LM interface |
| Execution       | pathlib, subprocess  | stdlib — no extra dependencies           |
| Config          | pydantic-settings    | Env var loading, `.env` support          |

### Layout

```
src/
  transition2exec/
    api/
      app.py          FastAPI app, /transition2exec endpoint
      models.py       Request/response models
    transition/
      dspy_module.py  Two-stage LLM pipeline (tool_sequence → dstt_format)
      providers.py    Backend wiring (qwen / stub)
      mapping.py      resolve_input, default_output_value
    tool_catalog.py   Grounded tool definitions (name, inputs, outputs)
    validation.py     Executable DSTT validation
    service.py        Orchestrates backend + validation
    config.py         Settings from env

prompts/
  tool_sequence.md    Stage 1 prompt — abstract tool → grounded tool plan
  dstt_format.md      Stage 2 prompt — plan → executable DSTT JSON
```

### Two-stage LLM pipeline (transition2exec)

```python
# Stage 1 — resolve abstract tool to grounded tool(s), plain text
stage1 = lm(tool_sequence_prompt(task, abstract_tool, context, tool_list))
# → "TOOL: exists\nINPUTS: file_path=/path/hello.py"

# Stage 2 — format as executable DSTT JSON
resolved = extract_resolved_tools(stage1, available_tools, state)
stage2 = lm(dstt_format_prompt(stage1, resolved))
# → {"status":"ok","segments":[{"transitions":[...],"milestone":[...]}]}
```

Stage 1 keeps the LLM output simple (plain text).
Stage 2 constrains it with a pre-resolved tool schema so the model cannot
hallucinate tool names or input keys.

### Tool dispatch (taskexecutor)

```python
TOOL_REGISTRY = {
    "exists":                   lambda state: {"is_present": Path(state["file_path"]).exists()},
    "read_file":                lambda state: {"text": Path(state["file_path"]).read_text()},
    "create_file":              lambda state: Path(state["file_path"]).write_text(state["content"]) or {"success": True},
    "run_shell_command":        lambda state: subprocess.run(state["command"], shell=True, ...),
    "subtask":                  lambda state: run_subtask(state["task"], state["context"], state["parent_task"]),
    # ...
}

def dispatch(tool_name, state):
    fn = TOOL_REGISTRY[tool_name]
    return fn(state)
```

### Subtask tool

```python
def run_subtask(task, context, parent_task):
    # 1. Check reduction
    if not is_subtask_of(task, parent_task):   # binary LLM call
        raise ValueError("subtask does not reduce parent task")

    # 2. Plan
    abstract_dstt = call_task2plan(task, context)

    # 3. Execute in new kernel instance
    return call_taskexec(task, context, abstract_dstt, parent_task=parent_task)
```


## 9. Open Decisions

- **Tool registry injection** — static registry at startup or dynamic registration
  via API? Current implementation is static.
- **Subtask reduction check** — binary LLM call format not yet specified.
  Should live in a `prompts/` file like the other LLM calls.
- **available_tools in transition2exec** — currently defaults to the built-in
  catalog. Runtime-provided tool lists would allow domain-specific grounding.
