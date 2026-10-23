#!/usr/bin/env python3
"""Suggest groups of objects that work together, as a starting point for capabilities.

Usage:
  cluster_objects.py inventory.json --out clusters.json [--max-size 15]

How it groups, in order:
  1. Families: an object and the detail objects that hang off it by master-detail.
  2. Families joined by lookups, strongest links first, while the group stays
     within --max-size objects.
  3. Objects with no links joined to the group whose members share the longest
     leading words of their names ('Advanced Account Forecast ...'); objects still
     on their own grouped with each other the same way.
On basis usage, objects that hold no records join no group either: they are listed under
unusedObjects, and the capability-grouper leaves them unassigned with that reason.
Hubs (objects many others reference, such as Account or Product) and platform
objects never join groups: a lookup to Account says nothing about which
capability an object belongs to. Polymorphic fields are ignored for the same
reason. The capability-grouper agent reads the result, names the capabilities
and decides; this script only proposes.

Exit 0 on success, 2 on a setup problem.
Standard library only; Python 3.8 or later.
"""

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import common
from common import SetupError

MD_WEIGHT, LOOKUP_WEIGHT = 3, 1  # master-detail binds objects more tightly than a lookup, so it joins groups first


class UnionFind:
    def __init__(self, items):
        self.parent = {i: i for i in items}
        self.size = {i: 1 for i in items}

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return a
        if (self.size[a], b) < (self.size[b], a):
            a, b = b, a
        self.parent[b] = a
        self.size[a] += self.size[b]
        return a


def common_prefix(word_lists):
    if not word_lists:
        return []
    prefix = []
    for column in zip(*word_lists):
        if len({w.casefold() for w in column}) == 1:
            prefix.append(column[0])
        else:
            break
    return prefix


def cluster(inv, max_size):
    objects = {o["apiName"]: o for o in inv["objects"]}
    unused = set(common.unused_objects(inv))  # basis usage: objects holding no records join no group
    business = sorted(a for a, o in objects.items() if o.get("role") not in ("platform", "hub") and a not in unused)
    hubs = sorted(a for a, o in objects.items() if o.get("role") == "hub")
    biz = set(business)
    names = {a: common.words(objects[a]["name"]) or common.words(a) for a in business}

    edges = []
    for rel in inv.get("relationships", []):
        a, b = rel["from"], rel["to"]
        if a in biz and b in biz and a != b and not rel.get("polymorphic"):
            edges.append((a, b, MD_WEIGHT if rel.get("kind") == "master-detail" else LOOKUP_WEIGHT))

    uf = UnionFind(business)
    for a, b, weight in edges:
        if weight == MD_WEIGHT:
            uf.union(a, b)

    def family_links():
        links = Counter()
        for a, b, weight in edges:
            ra, rb = uf.find(a), uf.find(b)
            if ra != rb:
                links[tuple(sorted((ra, rb)))] += weight
        return links

    while True:
        merged = False
        for (ra, rb), _ in sorted(family_links().items(), key=lambda kv: (-kv[1], kv[0])):
            ra, rb = uf.find(ra), uf.find(rb)
            if ra != rb and uf.size[ra] + uf.size[rb] <= max_size:
                uf.union(ra, rb)
                merged = True
                break
        if not merged:
            break

    linked = {a for a, b, _ in edges} | {b for a, b, _ in edges}

    def lead(api, k):
        return tuple(w.casefold() for w in names[api][:k])

    def singles():
        return [a for a in business if a not in linked and uf.size[uf.find(a)] == 1]

    # 3a. An unlinked object joins the group whose members share the most leading words with it.
    for single in singles():
        mine = names[single]
        best, best_key = None, (0, 0)
        groups = defaultdict(list)
        for other in business:
            if other != single:
                groups[uf.find(other)].append(other)
        for root, members in groups.items():
            if len(members) < 2 or uf.size[root] + 1 > max_size:
                continue
            for k in range(min(3, max(len(mine) - 1, 1)), 0, -1):
                sharing = [m for m in members if lead(m, k) == lead(single, k)]
                needed = 1 if k > 1 else 2
                if len(sharing) >= needed:
                    key = (k, len(sharing))
                    if key > best_key:
                        best, best_key = root, key
                    break
        if best is not None:
            uf.union(single, best)

    # 3b. Objects still on their own form groups by their shared leading words, longest first
    #     (with no relationships at all, 'Claim', 'Claim Item' and 'Claim Coverage' group this way).
    for k in (3, 2, 1):
        buckets = defaultdict(list)
        for api in singles():
            if len(names[api]) >= k:
                buckets[lead(api, k)].append(api)
        for key in sorted(buckets):
            members = buckets[key]
            if len(members) < 2:
                continue
            for start in range(0, len(members), max_size):
                chunk = members[start:start + max_size]
                for api in chunk[1:]:
                    uf.union(chunk[0], api)

    groups = defaultdict(list)
    for api in business:
        groups[uf.find(api)].append(api)
    ordered = sorted(groups.values(), key=lambda m: (-len(m), sorted(m)[0]))
    cluster_of = {}
    for index, members in enumerate(ordered, 1):
        for api in members:
            cluster_of[api] = f"cluster-{index}"

    md_children = {a for a, b, w in edges if w == MD_WEIGHT}
    inbound = Counter(b for a, b, _ in edges)
    hub_use = defaultdict(Counter)
    for rel in inv.get("relationships", []):
        if rel["from"] in biz and rel["to"] in hubs and not rel.get("polymorphic"):
            hub_use[cluster_of[rel["from"]]][rel["to"]] += 1
    cross = defaultdict(Counter)
    for a, b, weight in edges:
        if cluster_of[a] != cluster_of[b]:
            cross[cluster_of[a]][cluster_of[b]] += 1

    listed = {a for c in inv.get("capabilities", []) for a in c.get("objects", []) + c.get("sharedObjects", [])}
    out = []
    for index, members in enumerate(ordered, 1):
        cid = f"cluster-{index}"
        members = sorted(members, key=lambda a: (-inbound[a], a))
        prefix = common_prefix([names[m] for m in members])
        roots = [m for m in members if m not in md_children]
        suggested = " ".join(prefix) if prefix and len(members) > 1 else objects[roots[0] if roots else members[0]]["name"]
        entry = {"id": cid, "suggestedName": suggested, "size": len(members),
                 "members": [{"apiName": m, "name": objects[m]["name"], "kind": objects[m].get("kind", ""),
                              "referencedBy": inbound[m]} for m in members],
                 "rootObjects": roots}
        if hub_use[cid]:
            entry["hubsUsed"] = dict(hub_use[cid].most_common())
        if cross[cid]:
            entry["linksToOtherClusters"] = dict(cross[cid].most_common())
        if listed:
            orphans = [m for m in members if m not in listed]
            if orphans:
                entry["notInAnySourceCapability"] = orphans
        out.append(entry)

    referrers = defaultdict(set)
    for rel in inv.get("relationships", []):
        if rel["to"] in hubs and not rel.get("polymorphic") and rel["from"] in cluster_of:
            referrers[rel["to"]].add(cluster_of[rel["from"]])
    hub_rows = [{"apiName": h, "name": objects[h]["name"], "usedByClusters": len(referrers[h])} for h in hubs]
    hub_rows.sort(key=lambda r: (-r["usedByClusters"], r["apiName"]))
    platform = sorted(a for a, o in objects.items() if o.get("role") == "platform")
    result = {"maxSize": max_size, "clusters": out, "hubs": hub_rows, "platformObjects": platform}
    unused_business = sorted(a for a in unused if objects[a].get("role") not in ("platform", "hub"))
    if unused_business:
        # the capability-grouper lists these under unassigned, reason "Configured but holding no records"
        result["unusedObjects"] = [{"apiName": a, "name": objects[a]["name"]} for a in unused_business]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Suggest groups of related objects.")
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-size", type=int, default=15)
    args = parser.parse_args(argv)
    try:
        inv = common.load_json(args.inventory, "inventory")
        errors = common.shape_errors(inv, "inventory.schema.json")
        if errors:
            raise SetupError("the inventory does not match its schema; run inventory.py check first:\n  " + "\n  ".join(errors[:10]))
        result = cluster(inv, args.max_size)
    except SetupError as exc:
        print(f"SETUP {exc}", file=sys.stderr)
        return 2
    common.write_json(args.out, result)
    sizes = [c["size"] for c in result["clusters"]]
    singles = sum(1 for s in sizes if s == 1)
    print(f"{len(sizes)} group(s) of {sum(sizes)} object(s) ({singles} on their own), "
          f"{len(result['hubs'])} hub(s), {len(result['platformObjects'])} platform object(s)"
          f"{', ' + str(len(result['unusedObjects'])) + ' object(s) holding no records' if result.get('unusedObjects') else ''} left out; written to {args.out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
