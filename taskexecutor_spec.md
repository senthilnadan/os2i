TaskExecutor Spec
=================

Overview
--------
TaskExecutor is a runtime kernel that materialises and executes an AbstractDSTT.
It owns the execution loop, holds the tool registry, and uses state as the single
channel between all transitions.

For each abstract transition it calls transition2exec to compile it to a grounded
executable transition, patches the resolved inputs into state, dispatches the tool,
and merges the outputs back into state before moving to the next transition.


Architecture
------------

    ┌─────────────────────────────────────────────────────┐
    │  TaskExecutor                                        │
    │                                                      │
    │  tool registry (injected at startup)                 │
    │  ┌──────────────────────────────────────────────┐   │
    │  │ exists, read_file, create_file, ...          │   │
    │  │ run_shell_command                            │   │
    │  │ subtask  ← recursive kernel instance        │   │
    │  └──────────────────────────────────────────────┘   │
    │                                                      │
    │  DSTT Kernel                                         │
    │  ┌──────────────────────────────────────────────┐   │
    │  │ for each segment:                            │   │
    │  │   for each abstract_transition:              │   │
    │  │     1. compile  → transition2exec            │   │
    │  │     2. patch    → state.update(inputs)       │   │
    │  │     3. dispatch → tool(state)                │   │
    │  │     4. merge    → state.update(outputs)      │   │
    │  │   milestone reached → next segment           │   │
    │  └──────────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────┘


Endpoint
--------
POST /taskexec


Input
-----
{
  "task": "Check whether hello.py exists in the project folder.",
  "parent_task": null,
  "state": {
    "project_folder_path": "/path/to/project",
    "target_file": "hello.py"
  },
  "abstract_dstt": {
    "segments": [
      {
        "transitions": [
          {
            "id": "t1",
            "tool": "check_python_file_existence",
            "inputs": ["project_folder_path"],
            "outputs": ["python_file_exists"],
            "output_type": {"python_file_exists": "bool"},
            "complexityTime": "O(1)",
            "complexitySpace": "O(1)",
            "skill_required": ["programmer"],
            "resource_required": ["filesystem"]
          }
        ],
        "milestone": ["python_file_exists"]
      }
    ]
  }
}


Output
------
{
  "status": "completed",
  "state": {
    "project_folder_path": "/path/to/project",
    "target_file": "hello.py",
    "file_path": "/path/to/project/hello.py",
    "is_present": true
  },
  "execution_log": [
    {
      "transition_id": "t1",
      "tool": "exists",
      "inputs": {"file_path": "/path/to/project/hello.py"},
      "outputs": {"is_present": true},
      "status": "ok"
    }
  ],
  "segments_completed": 1,
  "milestone_reached": ["is_present"]
}

On failure:
{
  "status": "failed",
  "state": { ... },
  "execution_log": [
    {
      "transition_id": "t1",
      "tool": "exists",
      "inputs": {"file_path": "/path/to/project/hello.py"},
      "outputs": {},
      "status": "failed",
      "error": "..."
    }
  ],
  "segments_completed": 0,
  "milestone_reached": []
}


Execution Loop
--------------
for each segment in abstract_dstt.segments:

    for each abstract_transition in segment.transitions:

        1. COMPILE
           POST /transition2exec with:
             - task
             - context = current state
             - abstract_transition
           Returns executable_dstt with one or more grounded transitions.
           If status != "ok" → fail with error, stop.

        2. for each grounded_transition in executable_dstt.segments[0].transitions:

           a. PATCH STATE
              Merge grounded_transition.inputs into state.
              (transition2exec resolved concrete values — they live in state now.)

           b. DISPATCH
              Look up tool name in registry.
              Call tool, passing state as context.
              Tool reads its required keys from state.
              If tool not found or raises → fail, stop.

           c. MERGE OUTPUTS
              Merge tool outputs into state.

    milestone_reached += segment.milestone keys that are now in state.

Return completed status, final state, execution log, milestone_reached.


State
-----
State is the single channel between all transitions and all tools.

- Initialised from the request's `state` field (the runtime context).
- transition2exec contributes resolved concrete values (inputs patch).
- Tools read inputs from state and write outputs back to state.
- State grows cumulatively — nothing is removed during execution.
- Keys from earlier transitions remain available to later ones.


Tool Registry
-------------
Tools are injected into the kernel by TaskExecutor at startup.
The kernel is tool-agnostic — it dispatches by name only.

Built-in tools (filesystem / shell):

  exists(file_path)                        → is_present
  list_directory(directory_path)           → entries
  list_directory_recursive(directory_path) → entries
  read_file(file_path)                     → text
  create_file(file_path, content)          → success
  append_to_file(file_path, content)       → success
  delete_file(file_path)                   → deleted
  copy_file(source_path, destination_path) → copied
  move_file(source_path, destination_path) → moved
  make_directory(directory_path)           → created
  remove_directory(directory_path,
                   recursive)              → removed
  run_shell_command(command,
                    working_directory)     → stdout, stderr, return_code

Subtask tool:

  subtask(task, context, parent_task)      → milestone outputs of the subtask

  The subtask tool:
    1. Calls /task2plan with task + context to get an abstract_dstt.
    2. Spins up a new kernel instance with that abstract_dstt and context as state.
    3. Executes to completion (sequential, blocking).
    4. Returns the subtask's final milestone outputs to the parent state.

  The parent kernel blocks until the subtask completes before continuing to
  the next transition.

  Subtask carries a reference to its parent task. Before executing, the kernel
  asks: "Is this task a subtask of the parent task?" via an LLM check.

  - If yes → reduction confirmed, proceed with execution.
  - If no  → not a subtask of the parent, fail immediately with status "failed"
             and error "subtask does not reduce parent task".

  This is a single binary LLM call — lightweight, no depth counter needed.
  A genuine subtask (narrower scope, delegated step, concrete sub-problem)
  will pass. A repeated or unrelated task will fail.


Failure Handling
----------------
- Any failure (compile, dispatch, tool error) stops execution immediately.
- No silent fallbacks. No retries.
- Partial state (up to the failed transition) is returned in the response.
- The execution log records the error on the failed transition entry.
- status = "failed"


Seed Tasks
----------
┌────────────────────────────┬──────────────────────────┬─────────────────────────────────────────┐
│            Task            │       Grounded Tool      │          Key behaviour tested           │
├────────────────────────────┼──────────────────────────┼─────────────────────────────────────────┤
│ Check file exists          │ exists                   │ single transition, boolean output       │
├────────────────────────────┼──────────────────────────┼─────────────────────────────────────────┤
│ List directory             │ list_directory_recursive │ list output into state                  │
├────────────────────────────┼──────────────────────────┼─────────────────────────────────────────┤
│ Read file                  │ read_file                │ text output into state                  │
├────────────────────────────┼──────────────────────────┼─────────────────────────────────────────┤
│ Delete file                │ delete_file              │ side effect, deleted flag               │
├────────────────────────────┼──────────────────────────┼─────────────────────────────────────────┤
│ Create file                │ create_file              │ content input from state                │
├────────────────────────────┼──────────────────────────┼─────────────────────────────────────────┤
│ Append to file             │ append_to_file           │ chained — file_path reused across steps │
├────────────────────────────┼──────────────────────────┼─────────────────────────────────────────┤
│ Run shell command          │ run_shell_command        │ stdout/stderr/return_code into state    │
├────────────────────────────┼──────────────────────────┼─────────────────────────────────────────┤
│ Multi-step (create + read) │ create_file → read_file  │ state threading between transitions     │
├────────────────────────────┼──────────────────────────┼─────────────────────────────────────────┤
│ Subtask                    │ subtask                  │ recursive kernel, outputs into parent   │
└────────────────────────────┴──────────────────────────┴─────────────────────────────────────────┘


Open Questions
--------------
- Should /task2plan URL be configurable per kernel instance or global config?
- How are tool registry extensions provided at runtime (config file, injection API)?
- Should /task2plan URL be configurable per kernel instance or global config?
- How are tool registry extensions provided at runtime (config file, injection API)?
