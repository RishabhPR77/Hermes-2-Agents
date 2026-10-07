# Style guide — how M91 blog posts should read

Voice: senior engineer who has been woken at 3am by a real alert. Direct,
specific, useful. "We" for M91, "you" for the reader.

## Voice

- Write like a working engineer explaining the thing to another engineer.
- Hold a clear position ("this is the part teams get wrong", "for a two-human
  team a channel of one is usually enough"). No fence-sitting.
- Prefer concrete mechanisms over abstractions: say what a `SHARED` response
  actually does to everybody else's phone, not "responses are scoped".

## Specificity

- Every claim about products, behaviours, outages or numbers carries a source
  link (and a date for competitor claims).
- Name the real tools, frameworks and APIs involved (LangChain, LangGraph,
  Vercel AI SDK, OpenAI Agents SDK, MCP, PagerDuty, Twilio, etc.) when they
  are genuinely part of the story.
- Show working code examples for developer topics. Example inputs and outputs
  beat prose.

## Indian examples where natural

- ₹ amounts, UPI, payout batches, GST months, 2AM stock-market alerts, fintech
  recovery flows. Use them when they make the point sharper, never to pad.

## Rhythm

- Vary sentence length. Mostly short, some long.
- First paragraph answers the reader's main question directly.
- Headings follow the questions the post set out to answer.
- Lists only for real lists (steps, options, config values). Never force
  "exactly three items".