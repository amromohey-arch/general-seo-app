# Design Principles

Established by approaching this as a product designer would — research the
person first, map the journey, then design. Apply these to every UI/UX
decision in this project, not just onboarding.

## Design for the least technical persona, not the most

Two real personas exist: a technical user who wants control, and a
non-technical business owner with zero patience for anything that feels
like software configuration. If a flow works for the second person, it
works for the first. The reverse isn't true. Default every design decision
toward the second persona.

## Map the whole journey before designing screens

Before UI, write out the actual sequence of moments someone goes through,
start to finish: hears about it → signs up → describes their business →
sees their first real generated article → decides to trust it with more →
connects their real website → gets their first result → checks back later.

Find the specific moment someone would quit, and design that moment first,
not last. The likely drop-off point for a non-technical user is "connect
this to my real website" if that step feels technical in any way.

## Find the fastest path to an "aha" moment

Ask the minimum before generating something real. E.g.: "describe your
business in a couple sentences" → generate one full article immediately →
let the person react to something concrete *before* asking for more setup
or trust. People tolerate configuration after they've seen the payoff, not
before it.

## Progressive disclosure, not two products

One system: a simple default view (business description, a preset, one
connect button) and a collapsed "Advanced" panel (seed topics, tone
examples, funnel definitions, CSS/styling) for people who want to
hand-tune. Same data underneath, different depth of exposure. Never build
a separate "simple mode" product — build one system that reveals more of
itself on request.

## Conversation over forms, where it helps

"Tell me about your business" + the model extracts a structured profile +
the person confirms or corrects it, beats a form with fifteen labeled
fields for a non-technical user. Forms feel like paperwork. Conversation
feels like being asked about something you already know.

## Test the real flow on a real non-technical person before calling it done

Design intuition produces a strong first draft. Watching a real
non-technical person actually hesitate on a real screen is what finds
what's actually wrong with it. Don't skip this step for the sake of
shipping faster.
