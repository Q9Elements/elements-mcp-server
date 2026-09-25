# Across your orgs

Every other Elements skill answers about one org. This one compares all of them.

If your Space has more than one Salesforce org connected, you can ask your assistant to pull the
same information from each of them and lay the answers side by side, as a **report file you can
email**, not just a chat reply. Nobody who opens it needs Elements, an AI assistant, or a network
connection.

## Start here

After connecting, ask exactly this:

> **Give me an overview of our Salesforce orgs.**

Your assistant will list the orgs it found in your Space, grouped by implementation, and ask you to
confirm the list. Confirming is a real step, not a formality; that confirmed list is what gets
recorded in the report, so anyone reading it later knows exactly which orgs were included.

Then it pulls a snapshot from each org and writes a single HTML file. Open it in any browser.

**If something goes wrong, the failure is the diagnostic.** No Spaces found means your connection
isn't authorized yet. An empty org list means no orgs are connected, or your role doesn't grant
access to them: orgs you can't see are simply not included, which is by design. A missing
capability means licensing, not a fault. See [troubleshooting](troubleshooting.md).

## Prerequisites

- **More than one connected org** in the Space, or there's nothing to compare. With one org, your
  assistant points you to the single-org Org Diagnostic instead.
- **Pro Space with an Analytics Cloud license** for the health-summary dimensions. Enterprise Space is needed for the query-based inventory.
- **Your assistant must be able to run Python.** The report is produced by a script, not written by
  the model; that's what makes the numbers reproducible. Claude Code and the Codex CLI can do this
  out of the box. In Claude Desktop and claude.ai this needs code execution available.

Everything is read-only against Salesforce. The only things written are the snapshot files and the
report, on your own machine.

## What you can ask for

Three examples. They are demonstrations, not a menu; the whole point is that you can describe what
you actually want and get it.

### "What do we have, across all our orgs?"

A plain inventory. Per-org size, how much is managed-package versus built by your team, counts by
metadata type, and an as-of stamp for every org.

It makes no judgments at all: no rankings, no scores, nothing labelled good or bad. That restraint
is deliberate: it's the report you send to someone who needs the lay of the land without an argument
attached.

*What it typically shows:* six orgs totalling 124,590 metadata nodes, of which 64,071 were built by
you; one org 76% managed-package and another 0.7%, so their raw sizes say almost nothing about how
much each team actually built.

### "Which orgs need cleanup attention, and is that real, or just their size?"

A technical-debt comparison. The second half of that question is the point: any org with more in it
has more debt-shaped numbers, and a package-heavy org looks alarming for reasons that aren't its
team's doing.

So this one compares orgs against their peer group's median rather than ranking them, and it only
ranks measures where "higher is better" genuinely holds; documentation coverage, for example, never
raw counts.

*Rendering is deferred.* The pull methodology is available and the numbers it gathers are real, but
the report itself is being redesigned around extremes and spread before it ships again, so this one
currently stops at the gathered data rather than a finished page.

### "Has our sandbox diverged from production?"

Coming next. Comparing a production org against its sandbox needs no accumulated history, so it
works as soon as it ships, with one thing asked of you: Elements doesn't record which org is the
production one and which is its sandbox, so you tell your assistant which orgs to pair, once. It
won't guess from the names, and you'll see the pairing you chose on the report.

## Making it a trend

Every run saves a dated snapshot. Run the same report next week and it grows a trend section by
itself, with no extra setup, no configuration.

To refresh:

> **Refresh the multi-org snapshot.**

That pulls today's data, rewrites the derived numbers, and re-renders the report. Running it twice
in one day just overwrites that day.

Start manual. Once you know you want it regularly, your assistant can schedule the same operation,
Claude Code has scheduled agents, the Codex CLI has cron. Scheduled pulls decay quietly when an
org's connection expires, which is exactly why every report carries per-org as-of stamps and counts
stale orgs in its header: the decay shows up in the output instead of hiding.

## A worked customization

The shipped reports are a starting point. This is what changing one actually looks like:

> **You:** "The overview is useful but I don't care about page layouts. I want to see validation
> rules and record types instead, and I want the orgs grouped by region, not by implementation."
>
> **Assistant:** "I can do both. Validation rules and record types swap straight into the counted
> types; that's one extra call per org, no meaningful cost.
>
> Region isn't something Elements knows about; there's no region field on a connection. So I'd need
> you to tell me the grouping once, something like: EMEA is Production and EMEA Sandbox, AMER is
> the other three. I'll record that in the report so anyone reading it can see the grouping you
> chose rather than guessing at it.
>
> One thing to flag: two of your orgs haven't synced in over a month. I'll keep them in and flag
> them rather than dropping them silently, but their numbers are a month old, so region totals that
> include them are mixed-age. Want me to note that on the page?"
>
> **You:** "Yes, and add documentation coverage per region."
>
> **Assistant:** "Coverage needs care: the underlying number reads 0 both when nothing is
> documented and when there's nothing to document. Two of your orgs have no validation rules at all,
> so their validation-rule coverage would show as 0% next to an org that genuinely documents none of
> its 63. I'll blank those rather than score them, and say why on the page."

That exchange is the product working as intended: you asked for something bespoke, and the parts
that couldn't be answered honestly were named rather than faked.

## Why you can trust the numbers

- **Every number traces back.** Each figure on the page came from a row in a plain CSV, which came
  from a raw response saved on disk with the exact call that produced it. Two hops, walkable in a
  text editor. You can also just ask: *"where does this number come from?"*
- **Freshness is per-org and never inferred.** Each org carries the timestamp of its last successful
  sync. An org that has stopped syncing still returns complete, healthy-looking data; the stamp is
  the only thing that reveals it, so the stamp is always shown.
- **Gaps are stated, never filled.** If something couldn't be measured, the report says so where the
  value would have been. A `0` on the page always means a real, observed zero.
- **Comparisons are normalized first.** Managed-package components are separated from what your team
  built before anything is compared, because otherwise you're mostly comparing which packages people
  installed.
- **No statistics on small groups.** Outlier analysis needs at least eight comparable orgs. Below
  that you get the extremes and the spread, honestly labelled, instead of statistical language that
  the sample size can't support.

## Next steps

- [`skills.md`](skills.md): the full capability catalog.
- [`getting-started.md`](getting-started.md): connecting your client.
- [`troubleshooting.md`](troubleshooting.md): connection and capability issues.
