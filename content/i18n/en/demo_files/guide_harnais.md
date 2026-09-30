# Guide to the agent harness

WaveStack demonstration document, deliberately long: it is used to show delegation to a
sub-agent. Original text, not confidential.

## 1. The model and the harness

A language model does only one thing: it reads a sequence of tokens and predicts the most
likely continuation. It has no memory between two calls, no clock, no access to files and
no way of acting on the world. Everything that looks like an agent able to search, read,
calculate or write comes from the code around it: the harness.

The harness prepares the context before each call, reads the model's output, runs the
requested actions and decides whether to call the model again. Two agents built on the
same model can therefore behave very differently: the difference lies in the harness, not
in the model.

## 2. The context, a scarce resource

The context is the complete text the model reads at each call. Its size is bounded by the
model's context window, counted in tokens. Part of the window is reserved for the answer;
the rest is shared between the system prompt, the conversation history, the description
of the tools, the documents retrieved and the tool results.

Every token read costs computing time, especially on a computer without a graphics card:
a context twice as long takes roughly twice as long to read. A good harness therefore
saves context. It puts in only what serves the task, it removes what is no longer useful,
and it summarises what is too long.

## 3. Memory

Short-term memory reinjects the previous exchanges at each call: without it, the model
forgets everything from one message to the next. It grows at every turn, until it fills
the window. Several strategies keep it in check: the sliding window, which keeps only the
recent exchanges; compaction, which summarises the older exchanges; the removal of old
tool results, often the bulkiest.

Global memory, on the other hand, survives the conversation: it is a file that the
harness rereads at every turn and that the model can add to when it learns something
useful about the user.

## 4. Tools

A tool is a function the harness knows how to run: reading the time, calculating, reading
a file, querying a service. The harness describes each tool to the model, with its name,
what it does and its parameters. When the model wants to use one, it writes a call in an
agreed format; the harness spots it, checks the arguments, runs the tool and reinjects its
result into the context. The model never runs anything itself.

Tool descriptions have a cost: they take up context at every call, even when the tool is
not used. With dozens of tools, this cost becomes huge. Lazy loading reduces it: the
harness gives only one line per tool, and loads the full documentation only when the
model asks for it.

## 5. The agent loop and its bounds

An agent turn is a loop: call to the model, reading of the output, execution of the
requested tools, reinjection of the results, then a new call, until an answer without any
tool call. A loop without a limit can run forever, for example if the model keeps asking
for the same tool or writes malformed calls.

The harness therefore sets three bounds. The first limits the number of model calls in a
turn. The second limits the retries after a call that was refused, malformed or aimed at
an unknown tool. The third reserves a fixed space for the answer, so that an output that
is too long is cut cleanly instead of overflowing. When a bound is reached, the harness
stops the loop and explains why: it is code that decides, not the model.

## 6. Hooks

A hook is a piece of code the harness calls at a fixed point of the turn: when the
message is received, before each model call, before and after each tool, at the end of
the turn. A hook can let through, modify, block or ask a human for approval. It serves as
a guard (forbidding the reading of a sensitive folder), an audit log, a context injection
(today's date) or a human approval before anything goes out to the network. The model
cannot get round a hook, since it is not in the decision loop: the hook runs before or
after it.

## 7. Skills and progressive loading

A skill is a set of instructions for one type of request, for example writing meeting
minutes. As long as it is not used, only its name and description take up the context.
When a request calls for it, the model loads it through a meta-tool and its full
instructions join the context. The tokens of a skill are thus paid for only when it is
used.

## 8. The sub-agent

Some sub-tasks consume a lot of context for a short result: reading a long document to
extract five ideas from it, going through a web page to find a figure. If the main agent
does this work itself, the whole document enters its context and stays there for the rest
of the turn, then in the history of the following turns.

The harness can instead delegate the sub-task to a sub-agent. It is the same model, but
called in a clean context: a short system prompt, the task, and a few tools. The
sub-agent sees neither the conversation nor the main prompt. It reads the document,
draws the requested result from it, and only this result comes back into the main
context. The saving is direct: the thousands of tokens of the document stay in the
context of the sub-agent, which disappears once the task is done, and the main agent
receives only a few hundred tokens.

Delegation has its limits too. The sub-agent has its own bounds, tighter than those of
the main turn. If its context overflows or it does not succeed, the harness reinjects an
explicit error and the main turn carries on. And since the model is the same, delegating
does not make the work more intelligent: it makes it cheaper for the main context. On a
small local model, the two contexts are read one after the other by the same instance,
which shows in the duration of the turn.

## 9. Where the data goes

As long as everything runs on the workstation, nothing leaves: the model, the harness,
the files and the local tools stay on the machine. Network traffic appears as soon as a
tool queries a public service, a remote MCP server is connected, or the model itself is
hosted in the cloud. In that last case, each call sends the whole context to the
provider, sub-agent included. An honest harness shows this outbound traffic, displays its
exact content and lets a human approve it before it is sent.

## 10. Key takeaways

- The model predicts text; the harness turns it into an agent.
- Context is scarce: each brick of the harness adds tokens to it, with a gain and a
  cost.
- Tools, skills and documentation are loaded on demand to save context.
- Bounds and hooks are code: they decide in the model's place when they need to.
- The sub-agent isolates a bulky sub-task: only its result comes back into the main
  context.
