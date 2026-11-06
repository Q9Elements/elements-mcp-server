"""Apply the run's selected reference model to metadata attachment payloads."""
import json
from pathlib import Path


def selected_reference(*folders):
    """Use the nearest run context, starting with the drawing's connection."""
    for folder in folders:
        folder = Path(folder).resolve()
        for parent in (folder, *folder.parents):
            for name, keys in (("connection.json", ("refModelId",)),
                               ("execution-state.json", ("slots", "ref_model_id")),
                               ("scope.json", ("metadata", "refModelId")),
                               ("trace.json", ("refModelId",))):
                path = parent / name
                if not path.is_file():
                    continue
                value = json.loads(path.read_text(encoding="utf-8"))
                for key in keys:
                    value = value.get(key) if isinstance(value, dict) else None
                if value:
                    return value
                if name != "connection.json":
                    break
            else:
                continue
            break
    return None


def fill_reference(value, ref_model_id):
    """Fill missing identifiers in models and compiled plans; retain explicit scope."""
    changed = False
    if isinstance(value, dict):
        if value.get("type") == "metadata" and value.get("apiName") and not value.get("refModelId") and ref_model_id:
            value["refModelId"] = ref_model_id
            changed = True
        for child in value.values():
            changed = fill_reference(child, ref_model_id) or changed
    elif isinstance(value, list):
        for child in value:
            changed = fill_reference(child, ref_model_id) or changed
    return changed


def scope_model(model, path, workdir):
    fill_reference(model, selected_reference(workdir, Path(path).parent))
    return model


def unscoped_attachment_stop(value):
    """Refuse saved payloads that cannot identify their selected reference model."""
    if isinstance(value, dict):
        if value.get("type") == "metadata" and not value.get("refModelId"):
            return {"action": "stop", "reason": "Saved plan has a metadata attachment without refModelId.",
                    "how": "Start this drawing again from the model."}
        children = value.values()
    elif isinstance(value, list):
        children = value
    else:
        return None
    for child in children:
        stop = unscoped_attachment_stop(child)
        if stop:
            return stop
    return None
