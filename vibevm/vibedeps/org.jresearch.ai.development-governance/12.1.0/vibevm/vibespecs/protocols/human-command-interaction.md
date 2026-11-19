# Human command interaction

<a id="HC-001"></a>
**HC-001 — Explicit adoption and scope.**

Apply this topic only when the owning project explicitly adopts it in accepted
human-owned guidance. It governs an assistant asking a human to perform shell
or administrative work and return a result, including ordinary diagnostics and
setup outside governed Tasks. Installation, package updates and references do
not adopt it. It does not serialize autonomous agent tool calls or create a
Task, Step, checklist, approval gate, persistent interaction state or operator
tool. Existing local authority and stronger safety boundaries remain binding.

<a id="HC-002"></a>
**HC-002 — One human action and one coherent result.**

Normally present one self-contained next action, one human input and one
well-defined result to return per conversation interaction. The action may be
one command, a script or a paste-safe block containing many commands. Prefer
batching related independent, deterministic or internally conditioned commands
into one bounded action and one readable report, with clear sections, meaningful
errors and an overall outcome. Avoid separate manual invocations, multiple
independent copybacks, repetitive one-command exchanges and huge inscrutable
output. Command count is not the measure of an interaction.

Stop before an intermediate result needs human interpretation, a choice, new
permission or changes the safety of what follows. Request the next applicable
action after that result and its necessary disposition; do not assign a genuine
multi-stage procedure as simultaneous homework. A deterministic condition may
stay inside a block only within the already authorized safe action. Batching
must not hide privileged, destructive, network/session-disrupting, credential
or production operations or evade operator awareness or authorization.

<a id="HC-003"></a>
**HC-003 — Shell-appropriate copyback.**

Explain how to obtain and return one easily copied report in the actual shell.
For Bash, an enclosing script/group can combine appropriately delimited output.
For PowerShell, account for object formatting and separate output streams:
several independently pasted commands can interleave or format awkwardly. Use
an enclosing script block, function or script and explicit formatting, capture
or reporting as appropriate. Preserve meaningful failures and exit/result status;
neither the last successful command nor formatting alone proves overall success.
No particular idiom, including `Out-String`, is mandatory for every case.

The [worked Bash and PowerShell examples](../guides/human-command-interaction.md)
illustrate this topic, not a fixed implementation recipe. [PC-006](proportional-controls.md#PC-006)
retains control-effectiveness assessment and [PC-010](proportional-controls.md#PC-010)
retains reuse of sufficient proof; this topic owns the human action/copyback
pattern. References do not broaden those topics' applicability or adopt them.
