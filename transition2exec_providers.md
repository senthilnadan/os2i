# DSPy Model Strategy for Transition2Exec

# Reference: `references/providers.py` from Task2Plan.

## Intent
Leverage DSPy to encode a reasoning chain that mirrors Task2Plan's `Task2PlanChainOfThought`, but emit **executable** DSTT fragments grounded to the `grounded_tools.md` catalog. The DSPy program should accept the task text, context, constraints, and available tools, and return status+segments + validation notes.

## Key Components
1. **Backend Interface** – reuse the `PlannerBackend` abstraction (model_name + generate method). Transition2Exec will have:
   - `Transition2ExecBackend` (abstract base) mirroring the contract.
   - Concrete backends (`DSPyStubBackend`, `OpenAIExecBackend`, `OllamaExecBackend`).

2. **DSPy Program of Thought** – a twin-LM chain (reasoning + formatting) controlled by:
   - Strong instructions: focus on concrete inputs, tool catalog, 3-transition limit, chaining of outputs.
   - Input payload includes resolved context, tool signatures, and the abstract transition from the seed.
   - Output schema: status + segments + optional diagnostics.

3. **Tools Awareness** – the reasoning LM needs the tool catalog (names/signatures/descriptions). `grounded_tools.md` can be embedded in the system prompt or referenced by the formatting LM.

4. **Validation Hook** – after receiving LM output, run a fast schema check (Pydantic from `grounded_tools.md`) to ensure:
   - Every transition uses an approved tool name.
   - Inputs/outputs match the tool signature.
   - Chain integrity (`next.inputs ⊆ previous.outputs`).

5. **Stub Behavior** – for offline/demo runs, `DSPyStubBackend` should generate deterministic executable DSTTs (e.g., map `check_python_file_existence` to `exists`).

## Integration Notes
- Maintain the Task2Plan ordering (`intent → constraints → compose plan`) but adjust the semantics to emit a single/transitions using real tools.
- Include metadata (`meta.status`, `resolved_context`, etc.) so Transition2Exec can signal ambiguity or the need for retries.
- Keep DSPy instructions explicit about no tool invention and grounding to the provided catalog.

## Next Steps for Implementation
1. Extend the OS2I spec with DSPy backend structure (interfaces + helper functions).  
2. Add the DSPy program definitions (instructions, schema, helpers).  
3. Wire the backend to the tool catalog, context resolver, and executive DSTT validator.
