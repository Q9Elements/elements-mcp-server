# Quote Line Pricing

Explain how one Salesforce quote line's price was calculated. The playbook uses Quote Line Microscope and Elements evidence to answer pricing questions, explain calculator price rules, identify gaps in the available evidence, and answer follow-up questions.

## Install

### Claude Code

```text
/plugin marketplace add Q9Elements/elements-mcp-server
/plugin install elements-quote-line-pricing@elements
```

### Codex

```text
codex plugin marketplace add Q9Elements/elements-mcp-server
codex plugin add elements-quote-line-pricing@elements
```

Installed copies contain only the shipped playbook files.

## Prerequisites

1. Salesforce CPQ and Elements Quote Line Microscope (QLM) are installed in the org.
2. The user has the "Salesforce CPQ Admin" and "Elements Quote Line Microscope Admin" permission sets. Together they grant every CPQ and QLM read the playbook uses. Elements Quote Line Microscope Admin is the only set that grants access to the QLM objects. The playbook reads as that user, subject to object and field access and record sharing.

   - Access to contracted prices (`SBQQ__ContractedPrice__c`) and standard objects (`Account`, `Product2`, `PricebookEntry`, `Pricebook2`, `Organization`) comes from the user's profile.
   - Contracted prices also require record sharing on the parent account.
   - Block overage rates come from `OverageRate__c`, a custom field the CPQ administrator creates on Block Price (`SBQQ__BlockPrice__c`); when the field exists, the user also needs read access to it, which no CPQ permission set grants.

   A missing required field stops the analysis and identifies the access gap.
   
   An unreadable required object can mean the package is missing or the object is inaccessible; the playbook asks an administrator to check both.

   Missing optional access limits the answer, which says what could not be read. For example, an unreadable contracted price is reported as unreadable, not as an absent price.

   This copyable access list gives an administrator the object and field application programming interface (API) names to check when an access gap is reported:

```text
Required objects: SBQQ__QuoteLine__c, Q9_QLM__Quote_Line_Log__c, SBQQ__Quote__c
Required SBQQ__QuoteLine__c fields: Id, Name, LastModifiedDate, SBQQ__Quote__c, SBQQ__Product__c, SBQQ__PricingMethod__c, SBQQ__OriginalPrice__c, SBQQ__ListPrice__c, SBQQ__SpecialPrice__c, SBQQ__ProratedPrice__c, SBQQ__RegularPrice__c, SBQQ__CustomerPrice__c, SBQQ__PartnerPrice__c, SBQQ__NetPrice__c, SBQQ__Quantity__c
Optional objects: Q9_QLM__Price_Rule_Evaluation__c, Q9_QLM__Price_Action_Evaluation__c, SBQQ__ContractedPrice__c, Account, SBQQ__BlockPrice__c, SBQQ__DiscountTier__c, SBQQ__Dimension__c, SBQQ__PriceRule__c, SBQQ__PriceCondition__c, Organization, Product2, PricebookEntry, Pricebook2
Optional SBQQ__QuoteLine__c fields: Q9_QLM__Quote_Line_Logging_Enabled__c, SBQQ__UnitCost__c, SBQQ__OriginalUnitCost__c, SBQQ__MarkupRate__c, SBQQ__MarkupAmount__c, SBQQ__Markup__c, SBQQ__CostEditable__c
Optional Q9_QLM__Quote_Line_Log__c fields: Q9_QLM__Diagram_Url__c, Q9_QLM__Quote_Line_Log_String__c
Optional SBQQ__BlockPrice__c fields: SBQQ__Price__c, SBQQ__LowerBound__c, OverageRate__c
Optional SBQQ__DiscountTier__c fields: SBQQ__Price__c
Optional SBQQ__PriceRule__c fields: Name
Optional Organization fields: Id
```

3. The playbook reads the quote line, its QLM log and related CPQ records from Salesforce. The playbook needs a way to make those queries. The two supported routes are the Salesforce command-line interface (CLI) and the Salesforce Hosted Model Context Protocol (MCP) server.

   - **Salesforce CLI (recommended):** The `sf cli` is installed and an org alias is authenticated. The plugin's script runs every query and reads the results directly; the AI assistant copies nothing.
   - **Salesforce Hosted MCP server `platform/sobject-reads`:** This route is available when the CLI cannot be used. The administrator has activated `platform/sobject-reads` under MCP Servers in Setup, has created an External Client App, and has authenticated the Salesforce MCP server with the AI assistant. When using the Salesforce MCP server, the AI assistant runs each query and passes each result to the script, copying it when the result is shown in the conversation rather than saved to a file. AI assistants have gotten better at copying, but are not 100% foolproof. A copying slip can drop or change a value. The playbook can and does check result completeness and queried record identifiers (Ids), quote line names, and log-to-line links, but cannot detect changes to other values; a field other than a record Id dropped in copying is reported as not readable. Check any surprising figure against the quote line in Salesforce.
4. The core `elements` plugin is installed and connected to Elements, in an authorized space linked to the Salesforce org with its reference model synced.
5. **Optional price rule change history:** The Revenue Cloud flag is enabled in Elements, and `SBQQ__PriceRule__c`, `SBQQ__PriceCondition__c`, and `SBQQ__PriceAction__c` are selected on the org's Industries settings tab in Elements. History starts with the first sync after the flag and objects are set; earlier changes are unavailable. If history is unavailable, the answer says so and the analysis continues. Change history covers price rules, price conditions and price actions only; Elements does not sync quote, quote line or QLM records, so the playbook shows no change history for them.

## Run

On the quote line, click QLM "Create Diagram". Creating a QLM diagram also creates a Quote Line log record that is required by the playbook.

Start with “Why is this quote line priced this way?” or “Which price rules affected this quote line?” Provide the line identifier or name, your question, and your chosen data route; for the CLI route, provide the org alias. The playbook asks for missing inputs together. A new engagement defaults to the current working directory and reports that location. It saves your progress and answers in that directory.

To continue, say “Resume my quote line pricing explanation”. The playbook uses `execution-state.json` in the current working directory or a directory you supply, asking for the engagement directory only when it cannot find the state file. It continues an unfinished data collection for the same line. Naming a different line starts a fresh evidence directory. When the evidence is ready and the resume request has no question, it re-offers the latest answer, or asks what you would like to understand if no answer is saved. When you finish, it lists the quote lines it explained. Keep the engagement directory and its contents together.

## How answers are built

The playbook builds an explanation from the available pricing evidence and focuses follow-up answers on your question.

When a log holds several calculations, the playbook explains the last one, which produced the current price. If it cannot separate them, the answer says "Earlier calculation passes may be included in these figures."

List Price attribution requires agreement with the recorded value: a price rule's logged value, the option unit price, or the price book value must equal the line's List Price. When those sources do not agree and no other pricing method or manual edit explains it, the source is "not determined from the recorded data".

## Scope

The playbook reads Salesforce and Elements data and makes no changes in the org. It explains one quote line at a time. Price rule analysis covers calculator price rules captured by QLM; configurator-scope rules are outside this analysis.
