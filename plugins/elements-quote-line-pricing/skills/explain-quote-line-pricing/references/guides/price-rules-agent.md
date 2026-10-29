# Price Rules Agent guide

Read `priceRules`, `log`, `priceWaterfall.stages`, and relevant `warnings` and `accessGaps`.

`priceRules.passCountSource` records `markers` for log begin markers or `stage_order` for the stage-order fallback, including an ambiguous fallback with a null count.

`priceRules.passCount` counts calculation passes from the log string's `MARKER:On Initialization:-1` begin markers. A known count selects the final pass's evaluations and actions. Single-stage evaluations or tied or missing sequences without corroborating markers give a null count and retain all evaluations; the answer says "Earlier calculation passes may be included in these figures." Treat those figures as potentially spanning calculations. An empty evaluation set without markers has a count of zero.

`priceRules.status` distinguishes `rules_fired`, `no_rules_fired`, `no_log`, `not_readable`, and `query_failed`. A missing log or failed read cannot establish that no rule fired. For each relevant `priceRules.rules` entry, use its event, evaluation order and sequence, name, actions and conditions. Order actions by their recorded sequence. `rulesWithoutActions` identifies logged rules with no logged action; say they made no logged change, not that every possible rule was evaluated.

An action's `valueAfterRule` is the field's value after the rule's actions ran, as text; it is not necessarily the value written by that individual action, and the earlier value is not captured. Use the script's `impact` tag: direct actions map to a price waterfall stage; indirect actions do not. Use `waterfallStage` and `priceWaterfall.stages[].ruleWrites` to relate a direct action to the recorded stage, without claiming the action alone caused a difference. Do not perform discount arithmetic. Do not speculate about why a rule exists.

Quote logged stored values exactly as recorded.

Calculation proceeds through related data, On Initialization rules, formulas, Before Calculate rules, quantities, On Calculate rules, native pricing, After Calculate rules, then formulas and totals. Conditions in the same event are evaluated before actions. A rule reading a formula at initialization may not have the calculated value; a List or Special write at On Calculate or earlier can flow through native pricing. An After Calculate unit-price write can leave the waterfall stale until another calculation. A rule writing Special Price needs Special Price Type set to Custom for that price to take effect; identify a possible issue only when the available action evidence supports it. Condition and action definitions beyond the recorded fields are not established here.

Leave history limits to the composed answer.

Elements history can show who changed a rule, condition or action and when. Comment on notable changes, such as a recent change or who made it, without listing every rule. For before-and-after field values, open that component's history in Elements. If history is unavailable, report the gap rather than saying no change occurred.
