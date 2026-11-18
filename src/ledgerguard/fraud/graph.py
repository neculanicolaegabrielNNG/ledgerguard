from __future__ import annotations

from collections import deque
from typing import Any

from ledgerguard.common.ports import TransferFact

SUSPICIOUS_STATES = ("under_review", "blocked")
CYCLE_NODE_LIMIT = 2000


def _reachable(adjacency: dict[str, set[str]], start: str) -> set[str]:
    seen: set[str] = set()
    queue: deque[str] = deque(adjacency.get(start, set()))
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        queue.extend(adjacency.get(node, set()) - seen)
    return seen


# ————————————————————————————————————————

def cycle_nodes(adjacency: dict[str, set[str]]) -> set[str]:
    nodes = set(adjacency) | {target for targets in adjacency.values() for target in targets}
    if len(nodes) > CYCLE_NODE_LIMIT:
        return set()
    return {node for node in nodes if node in _reachable(adjacency, node)}


# ————————————————————————————————————————

def _components(nodes: set[str], edges: set[tuple[str, str]]) -> list[set[str]]:
    neighbors: dict[str, set[str]] = {node: set() for node in nodes}
    for source, target in edges:
        neighbors[source].add(target)
        neighbors[target].add(source)
    seen: set[str] = set()
    result: list[set[str]] = []
    for node in sorted(nodes):
        if node in seen:
            continue
        component: set[str] = set()
        queue: deque[str] = deque([node])
        while queue:
            current = queue.popleft()
            if current in component:
                continue
            component.add(current)
            queue.extend(neighbors[current] - component)
        seen |= component
        result.append(component)
    return result


# ————————————————————————————————————————

def build_graph(facts: list[TransferFact]) -> dict[str, Any]:
    aggregated: dict[tuple[str, str], dict[str, Any]] = {}
    adjacency: dict[str, set[str]] = {}
    flagged_nodes: set[str] = set()
    for fact in facts:
        key = (fact.from_account_id, fact.to_account_id)
        entry = aggregated.setdefault(key, {"count": 0, "amount_ron_minor": 0, "flagged": False})
        entry["count"] += 1
        entry["amount_ron_minor"] += fact.amount_ron_minor
        adjacency.setdefault(fact.from_account_id, set()).add(fact.to_account_id)
        if fact.state in SUSPICIOUS_STATES:
            entry["flagged"] = True
            flagged_nodes.update(key)
    nodes = {account for key in aggregated for account in key}
    in_cycle = cycle_nodes(adjacency)
    suspicious = in_cycle | flagged_nodes
    clusters = [
        sorted(component)
        for component in _components(nodes, set(aggregated))
        if len(component) >= 2 and component & suspicious
    ]
    return {
        "nodes": [
            {
                "id": node,
                "suspicious": node in suspicious,
                "reasons": [
                    reason
                    for reason, active in (("cycle", node in in_cycle), ("flagged_transfer", node in flagged_nodes))
                    if active
                ],
            }
            for node in sorted(nodes)
        ],
        "edges": [
            {"source": source, "target": target, **values} for (source, target), values in sorted(aggregated.items())
        ],
        "clusters": clusters,
    }
