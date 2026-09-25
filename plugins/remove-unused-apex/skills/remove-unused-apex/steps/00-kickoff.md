# 00 Kickoff

State: `kickoff`

## Purpose

Open the engagement with the customer's checklist and establish the local engagement state before
any organization check runs.

## Procedure

1. Print this block before doing anything:

   > **Unused Apex engagement kickoff**
   >
   > The Unused Apex playbook runs autonomously once we get two inputs from you and one access check
   > passes:
   >
   > 1. We need the Setup Apex Classes banner's displayed percentage and allocation. Paste the banner
   >    into the chat. We record the exact current character count when it is available.
   > 2. We need to know how much Apex capacity you want back: a percentage of your allocation to free
   >    (for example 5%), the usage you want to end at (for example 85%), or a number of characters. A
   >    target usage percentage requires the exact current character count; when the banner does not
   >    show it, we ask you once to restate the target as a percentage to free or a number of
   >    characters.
   >
   > **Access check.** We manage the LLM context by creating CSV files in AWS S3. Your agent needs
   > access to those files. We'll ping the endpoint; if we can't reach it, you will need to ask your IT
   > to whitelist it.
   >
   > Nothing in this engagement deletes or changes anything in the organization.

   In the block, API is application programming interface, LLM is large language model, CSV is
   comma-separated values, AWS S3 is Amazon Web Services Simple Storage Service, and IT is information
   technology.

   The prose version for customer support is `references/kickoff-checklist.md`.
2. Establish the engagement directory by asking where the engagement lives or taking the working
   directory. Copy `templates/execution-state.json` into that directory as `execution-state.json`.
   Record `engagement.name` and `engagement.started` in the copied state file.
3. Apply outcome TR-16.

## Outcomes

- **TR-16 — the kickoff block is printed and the state file exists.** Write
  `{"current_state": "ready", "current_step": "steps/01-check-prerequisites.md"}`. Next card:
  `steps/01-check-prerequisites.md`, when the customer resumes.

## Stop rule

Stop after writing `ready`. The customer resumes when the banner is pasted, the capacity target is
stated, and the bundle host is reachable.

## Failure

If the engagement directory cannot be established, say what is needed and stop with no state file
written.
