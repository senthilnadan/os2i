Convert these resolved tool templates into an executable DSTT JSON.

resolved_tools (each entry is a fully-populated transition template — all values already resolved):
{resolved_tools}

Rules:
- Copy each tool's template exactly. Replace "t?" with sequential ids starting at t1, t2, etc.
- inputs: copy values exactly as given. Do not add, remove, or change any keys or values.
- outputs: all values must be null.
- milestone: list of output key names from the last transition's outputs.
- Only include tools from resolved_tools. No extra tools, no extra keys.
- Each tool produces exactly ONE transition object with id, tool, inputs, and outputs together. Never split a transition.
- If resolved_tools is "(none matched)" respond with: {{"status":"not_mappable","segments":[]}}

Respond with ONLY valid JSON, no extra text:
{{"status":"ok","segments":[{{"transitions":[{{"id":"t1","tool":"<name>","inputs":{{"<key>":"<value>"}},"outputs":{{"<key>":null}}}}],"milestone":["<output_key>"]}}]}}
