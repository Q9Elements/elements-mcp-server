# Kickoff checklist

The Unused Apex playbook runs autonomously once the customer supplies two inputs and one access check
passes.

1. The customer pastes the Setup Apex Classes banner into the chat. The playbook reads its displayed
   percentage and allocation and records the exact current character count when it is available.
2. The customer states how much Apex capacity to recover: a percentage of the allocation to free
   (for example 5%), a usage percentage to end at (for example 85%), or a number of characters. A
   target usage percentage requires the exact current character count; when the banner does not show
   it, the playbook asks the customer once to restate the target as a percentage to free or a number
   of characters.

**Access check.** We manage the LLM context by creating CSV files in AWS S3. Your agent needs access to
those files. We'll ping the endpoint; if we can't reach it, you will need to ask your IT to whitelist it.

API is application programming interface, LLM is large language model, CSV is comma-separated values,
AWS S3 is Amazon Web Services Simple Storage Service, and IT is information technology.

Nothing in this engagement deletes or changes anything in the organization.
