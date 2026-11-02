# Working in this repo

The founder's standing rules and the design questions to answer for every feature are in `docs/design-checklist.md`. Read it before building. Do not break old
behaviour; keep it simple; think wider than the case in front of you; be proactive. The rules below add to it. They are adapted from the guidelines in
github.com/multica-ai/andrej-karpathy-skills (MIT; written by a third party, not by Karpathy), kept to what the checklist does not already say.

**Surgical changes.** Every changed line should trace to the request. Match the surrounding code's style, comments and naming even where you would do it
differently. Do not tidy adjacent code. If you notice unrelated dead code or a bug, say so and leave it. Remove only the imports, variables and functions your own
change made unused.

**State assumptions.** If a request has more than one reading, name them and ask, or pick one and say which. If something is unclear, say what is unclear before
building on a guess.

**Verifiable goals.** Turn a task into a check before starting: a bug gets a test that fails first; new behaviour gets a test of the case and of the old case beside
it; a refactor is judged by the same tests passing before and after. For several steps, state the plan with the check for each. Run the suite with
`scripts/test.sh`, never pytest directly (see the checklist on why).

**Report what is true.** Say what was run and what was not. "Passes" means the suite was run; "not exercised" means it was not.
