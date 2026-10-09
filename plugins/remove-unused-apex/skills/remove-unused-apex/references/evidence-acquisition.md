# Evidence acquisition

The customer supplies the Setup Apex Classes banner and states the capacity target. Elements captures the
remaining evidence. The playbook changes nothing in the organization.

## Bundle host reachability

The instance is the Elements host that the Model Context Protocol (MCP) connector points at. Select
the bundle host from this table. The host in the tool's `bundleUrl` is authoritative when card 02
receives it.

| instance | connector host | bundle host |
|---|---|---|
| European Union (EU) production | `app.q9elements.com` | `production-elements-content-668783629007-eu-west-1.s3.eu-west-1.amazonaws.com` |
| United States (US) production | `us.elements.cloud` | `production-elements-content-448905033567-us-east-2.s3.us-east-2.amazonaws.com` |
| Other | Any other connector host | Ask Elements support for the host |

From the environment that will download the bundle, run:

`curl -sS -o /dev/null --max-time 10 -w '%{http_code}' https://<host>/`

Any Hypertext Transfer Protocol (HTTP) status means the host is reachable. Amazon Web Services (AWS)
Simple Storage Service (S3) returns 403 to an unsigned request. Curl exit 6, 7, or 28 blocks the check
because of Domain Name System (DNS) failure, connection refused, or timeout. Print the exact host the
customer's information technology (IT) team must allow, record it in `open_items`, stay on `ready`,
and stop until the same probe passes.

This reachability governs the bundle download only, not Model Context Protocol (MCP) calls.

## Capacity figures from Setup

Open **Setup > Apex Classes** and copy the banner text, or capture a screenshot:

> Percent of Apex Used: N%. You are currently using N characters of Apex Code (excluding comments and
> @isTest annotated classes) in your organization, out of an allowed limit of N characters. The amount
> in use includes both Apex Classes and Triggers defined in your organization.

Record the displayed percentage, allowed limit, and capture time under `capacity` in
`execution-state.json`. Record exact characters used when the banner supplies that integer; omit it
when unknown. The limit interprets the percentage, and the optional used figure confirms the
counted-character total. Record the banner read time as `capacity.readAt`.

## Capacity target

Record the customer's wording and normalize it as `free_percent`, `target_percent`, or `characters`.
Use exact banner characters and allocation. A `target_percent` target needs the exact current
character count; when the banner does not show it, card 01 asks the customer once to restate the
target as a percentage to free or a number of characters. Do not add T-1's reconciliation tolerance to the target.
When the target usage is already met, record zero required characters and keep running the evidence
engagement.
