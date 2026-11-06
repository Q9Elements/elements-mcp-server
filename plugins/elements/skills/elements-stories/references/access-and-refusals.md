# Access and refusals

Preserve refusal `error`, `flag`, `message`, and any `hint` or `permission`. Quote a refusal's `message` as returned: it names what is missing, such as a role or access to a map.

When a feature refusal hints to switch spaces, resolve the user's intended authorized space with `get_space_context`, select it with `set_active_space`, and retry there; the hint can accompany any missing flag when another granted space satisfies all flags for that tool and mode, while resource permission is checked separately. Report `unauthorized_space` or `feature_not_enabled` as returned.

A refusal with `error: "missing_required_scope"` and `requiredScope: "mcp:stories:write"` means the connection's grant lacks that scope. Ask the user to reconnect the Elements connector so the grant includes it, then retry.

Item-level refusals inside a successful response (for example `no_access` on a link or `invalid_field` on an item) are per-item results, distinct from call-level refusals; report each beside its item.
