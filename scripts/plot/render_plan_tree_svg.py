#!/usr/bin/env python3
"""
Render a PlanTree JSON export into an SVG task tree (layered or radial).

Example:
  scripts/plot/render_plan_tree_svg.py --input plan_12.json --layout radial
"""

from __future__ import annotations

import argparse
import json
import math
import re
import textwrap
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

FONT_FAMILY = '"Helvetica Neue", "Helvetica", "Arial", sans-serif'
FONT_SIZE = 10
LINE_HEIGHT = 14
MAX_CHARS_PER_LINE = 20
MAX_LINES = 3
CHAR_WIDTH = 6.0

NODE_PADDING_X = 14
NODE_PADDING_Y = 10
NODE_WIDTH = NODE_PADDING_X * 2 + MAX_CHARS_PER_LINE * CHAR_WIDTH
NODE_HEIGHT = NODE_PADDING_Y * 2 + MAX_LINES * LINE_HEIGHT

H_GAP = 48
V_GAP = 90
RADIUS_STEP = 160

MARGIN = 60
TITLE_FONT_SIZE = 32
TITLE_HEIGHT = 26
OUTLINE_TOP_MARGIN = 32

OUTLINE_MAX_CHARS_PER_LINE = 64
OUTLINE_MAX_LINES = 2
OUTLINE_LINE_HEIGHT = 15
OUTLINE_LABEL_SIZE = 12
OUTLINE_CHAR_WIDTH = 6.0
OUTLINE_DETAIL_MAX_CHARS = 84
OUTLINE_DETAIL_MAX_LINES = 3
OUTLINE_DETAIL_FONT_SIZE = 11
OUTLINE_DETAIL_LINE_HEIGHT = 15
OUTLINE_DETAIL_CHAR_WIDTH = 6.0
OUTLINE_DETAIL_GAP = 6
OUTLINE_DETAIL_LABEL_GAP = 10
OUTLINE_PADDING_X = 16
OUTLINE_PADDING_Y = 12
OUTLINE_STRIPE_WIDTH = 8
OUTLINE_BADGE_HEIGHT = 16
OUTLINE_BADGE_PADDING_X = 6
OUTLINE_BADGE_GAP = 8
OUTLINE_ATTR_GAP = 6
OUTLINE_ATTR_HEIGHT = 18
OUTLINE_INDENT = 28
OUTLINE_GAP = 18
OUTLINE_MIN_WIDTH = 520
OUTLINE_MAX_WIDTH = 980
OUTLINE_BRACKET_OFFSET = 34
OUTLINE_BRACKET_WIDTH = 10
OUTLINE_BRACKET_RADIUS = 8
OUTLINE_BRACKET_MIN_HEIGHT = 36
ATTR_FONT_SIZE = 9
ATTR_CHAR_WIDTH = 5.4
ATTR_PADDING_X = 6
ATTR_GAP = 6

DEPTH_COLORS = [
    "#9FD6D2",
    "#F4C7A2",
    "#A5C8E8",
    "#BFE3B4",
    "#F0A9A1",
    "#D7D9A5",
]

ATTRIBUTE_COLORS = {
    "type": "#2F6F6B",
    "id": "#4E79A7",
    "depth": "#59A14F",
    "position": "#EDC948",
    "deps": "#F28E2B",
    "meta": "#E15759",
    "path": "#76B7B2",
}


@dataclass
class PlanNode:
    node_id: int
    label: str
    parent_id: Optional[int]
    position: int = 0
    children: List["PlanNode"] = field(default_factory=list)
    depth: int = 0
    x: float = 0.0
    y: float = 0.0
    angle: float = 0.0
    radius: float = 0.0
    subtree_width: float = 0.0
    leaf_count: int = 1
    is_virtual: bool = False
    lines: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    order_code: str = ""
    outline_lines: List[str] = field(default_factory=list)
    outline_attrs: List[Tuple[str, str, str]] = field(default_factory=list)
    outline_details: List[Tuple[str, List[str]]] = field(default_factory=list)
    outline_detail_count: int = 0
    outline_badge_width: float = 0.0
    outline_height: float = 0.0
    outline_detail_label_width: float = 0.0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a PlanTree JSON export into a publication-ready SVG."
    )
    parser.add_argument("--input", required=True, type=Path, help="PlanTree JSON file.")
    parser.add_argument("--output", type=Path, help="Output SVG path.")
    parser.add_argument(
        "--layout",
        choices=["layered", "radial", "outline"],
        default="layered",
        help="Layout style (layered, radial, or outline).",
    )
    parser.add_argument("--node-id", type=int, help="Render only the specified node.")
    parser.add_argument(
        "--exclude-children",
        action="store_true",
        help="When --node-id is provided, render only that node.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        help="Limit rendering depth (0 renders only the root).",
    )
    parser.add_argument(
        "--show-fields",
        default="id,type,depth,deps,meta",
        help=(
            "Comma-separated node attributes to show in outline layout. "
            "Options: id,type,depth,position,deps,meta. Use 'none' to hide."
        ),
    )
    parser.add_argument(
        "--detail-fields",
        default="instruction,context,context_sections,context_meta",
        help=(
            "Comma-separated detail fields to show in outline layout. "
            "Options: instruction,context,context_meta,context_sections. Use 'none' to hide."
        ),
    )
    parser.add_argument(
        "--max-meta-keys",
        type=int,
        default=3,
        help="Max metadata keys to show in outline layout.",
    )
    parser.add_argument(
        "--truncate-details",
        action="store_true",
        help="Truncate instruction/context/section detail lines (off by default).",
    )
    parser.add_argument(
        "--pattern",
        choices=["dots", "grid", "none"],
        default="dots",
        help="Background pattern to apply when not transparent.",
    )
    parser.add_argument(
        "--outline-timeline",
        action="store_true",
        help="Render a subtle vertical timeline with dots in outline layout.",
    )
    parser.add_argument(
        "--hide-title", action="store_true", help="Hide the plan title."
    )
    parser.add_argument(
        "--transparent", action="store_true", help="Use a transparent background."
    )
    return parser.parse_args(argv)


def clean_label(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"^(ROOT|COMPOSITE|ATOMIC):\s*", "", text, flags=re.IGNORECASE)
    return " ".join(text.split()) or "Untitled task"


def wrap_label(label: str, max_chars: int, max_lines: int) -> List[str]:
    lines = textwrap.wrap(
        label,
        width=max_chars,
        break_long_words=True,
        break_on_hyphens=False,
    )
    if not lines:
        return ["Untitled task"]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        trimmed = lines[-1][: max(0, max_chars - 3)].rstrip()
        lines[-1] = f"{trimmed}..."
    return lines


def to_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return f"{text[: max_chars - 3]}..."


def format_list(values: Iterable[object], max_items: int, max_chars: int) -> str:
    items = [str(item) for item in values if item is not None]
    if not items:
        return ""
    head = items[:max_items]
    suffix = ""
    if len(items) > max_items:
        suffix = f" +{len(items) - max_items}"
    return truncate_text(", ".join(head) + suffix, max_chars)


def parse_fields(raw: str) -> List[str]:
    valid = {"type", "id", "depth", "position", "deps", "meta"}
    aliases = {"pos": "position", "dep": "deps", "metadata": "meta"}
    value = (raw or "").strip().lower()
    if not value or value == "none":
        return []
    fields: List[str] = []
    for part in value.split(","):
        part = part.strip().lower()
        if not part:
            continue
        part = aliases.get(part, part)
        if part in valid:
            fields.append(part)
    if "id" in fields and "type" in fields:
        reordered = [field for field in fields if field not in {"id", "type"}]
        fields = ["id", "type"] + reordered
    return fields


def parse_detail_fields(raw: str) -> List[str]:
    valid = {"instruction", "context", "context_meta", "context_sections"}
    aliases = {"ctx": "context", "ctx_meta": "context_meta"}
    value = (raw or "").strip().lower()
    if not value or value == "none":
        return []
    fields: List[str] = []
    for part in value.split(","):
        part = part.strip().lower()
        if not part:
            continue
        part = aliases.get(part, part)
        if part in valid:
            fields.append(part)
    return fields


def lighten_hex(hex_color: str, ratio: float = 0.82) -> str:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        return hex_color
    r = int(color[0:2], 16)
    g = int(color[2:4], 16)
    b = int(color[4:6], 16)
    r = int(r + (255 - r) * ratio)
    g = int(g + (255 - g) * ratio)
    b = int(b + (255 - b) * ratio)
    return f"#{r:02X}{g:02X}{b:02X}"


def wrap_detail_value(text: str, max_chars: int, truncate: bool) -> List[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    if truncate:
        return wrap_label(cleaned, max_chars, OUTLINE_DETAIL_MAX_LINES)
    return textwrap.wrap(
        cleaned,
        width=max_chars,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [cleaned]


def load_plan_nodes(data: Dict) -> Tuple[Dict[int, PlanNode], str]:
    nodes_data = data.get("nodes")
    if not isinstance(nodes_data, dict) or not nodes_data:
        raise ValueError("Plan JSON does not contain a valid nodes map.")
    title = (data.get("title") or "Plan").strip() or "Plan"

    nodes: Dict[int, PlanNode] = {}
    for key, node in nodes_data.items():
        node_id = to_int(node.get("id") if isinstance(node, dict) else None)
        if node_id is None:
            node_id = to_int(key)
        if node_id is None:
            continue
        name = node.get("name") if isinstance(node, dict) else None
        position = to_int(node.get("position") if isinstance(node, dict) else None) or 0
        parent_id = to_int(node.get("parent_id") if isinstance(node, dict) else None)
        label = clean_label(name or f"Task {node_id}")
        nodes[node_id] = PlanNode(
            node_id=node_id,
            label=label,
            parent_id=parent_id,
            position=position,
            lines=wrap_label(label, MAX_CHARS_PER_LINE, MAX_LINES),
            raw=node if isinstance(node, dict) else {},
        )
    for node in nodes.values():
        if node.parent_id is not None and node.parent_id in nodes:
            nodes[node.parent_id].children.append(node)
    for node in nodes.values():
        node.children.sort(key=lambda child: (child.position, child.node_id))
    return nodes, title


def collect_subtree_ids(root: PlanNode, max_depth: Optional[int]) -> List[int]:
    selected: List[int] = []
    stack: List[Tuple[PlanNode, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        if max_depth is not None and depth > max_depth:
            continue
        selected.append(current.node_id)
        for child in current.children[::-1]:
            stack.append((child, depth + 1))
    return selected


def filter_nodes(
    nodes: Dict[int, PlanNode],
    roots: List[PlanNode],
    focus_id: Optional[int],
    include_children: bool,
    max_depth: Optional[int],
) -> Tuple[Dict[int, PlanNode], List[PlanNode]]:
    if focus_id is not None:
        if focus_id not in nodes:
            raise ValueError(f"Node id {focus_id} not found in plan.")
        focus = nodes[focus_id]
        if include_children:
            selected_ids = set(collect_subtree_ids(focus, max_depth))
        else:
            selected_ids = {focus_id}
    else:
        if max_depth is None:
            selected_ids = set(nodes.keys())
        else:
            selected_ids = set()
            for root in roots:
                selected_ids.update(collect_subtree_ids(root, max_depth))

    filtered: Dict[int, PlanNode] = {}
    for node_id in selected_ids:
        original = nodes[node_id]
        filtered[node_id] = PlanNode(
            node_id=original.node_id,
            label=original.label,
            parent_id=original.parent_id,
            position=original.position,
            lines=list(original.lines),
            raw=dict(original.raw),
        )
    for node in filtered.values():
        if node.parent_id is not None and node.parent_id in filtered:
            filtered[node.parent_id].children.append(node)
    for node in filtered.values():
        node.children.sort(key=lambda child: (child.position, child.node_id))

    new_roots = [node for node in filtered.values() if node.parent_id not in filtered]
    for root in new_roots:
        root.parent_id = None
    return filtered, new_roots


def ensure_single_root(roots: List[PlanNode], title: str) -> PlanNode:
    if len(roots) == 1:
        return roots[0]
    virtual = PlanNode(
        node_id=-1,
        label=clean_label(title or "Plan"),
        parent_id=None,
        position=0,
        is_virtual=True,
        lines=wrap_label(clean_label(title or "Plan"), MAX_CHARS_PER_LINE, MAX_LINES),
    )
    for root in sorted(roots, key=lambda node: (node.position, node.node_id)):
        root.parent_id = virtual.node_id
        virtual.children.append(root)
    return virtual


def iter_nodes(root: PlanNode) -> Iterable[PlanNode]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        for child in node.children[::-1]:
            stack.append(child)


def assign_depths(root: PlanNode, depth: int = 0) -> None:
    root.depth = depth
    for child in root.children:
        assign_depths(child, depth + 1)


def assign_order_codes(root: PlanNode) -> None:
    def _assign(node: PlanNode, prefix: str) -> None:
        node.order_code = prefix
        for idx, child in enumerate(node.children, start=1):
            child_prefix = f"{prefix}.{idx}" if prefix else str(idx)
            _assign(child, child_prefix)

    if root.is_virtual:
        root.order_code = ""
        for idx, child in enumerate(root.children, start=1):
            _assign(child, str(idx))
    else:
        _assign(root, "1")


def infer_node_type(node: PlanNode) -> str:
    if node.is_virtual:
        return "virtual"
    if node.parent_id is None:
        return "composite"
    if node.children:
        return "composite"
    return "atomic"


def collect_attributes(
    node: PlanNode, fields: List[str], max_meta_keys: int
) -> List[Tuple[str, str, str]]:
    attrs: List[Tuple[str, str, str]] = []
    raw = node.raw

    if "type" in fields:
        attrs.append(("Type", infer_node_type(node), "type"))
    if "id" in fields:
        attrs.append(("ID", str(node.node_id), "id"))
    if "depth" in fields:
        attrs.append(("Depth", str(node.depth), "depth"))
    if "position" in fields:
        pos_value = raw.get("position", node.position)
        if pos_value is not None:
            attrs.append(("Pos", str(pos_value), "position"))
    if "deps" in fields:
        deps = raw.get("dependencies") or raw.get("dependency_ids") or []
        if isinstance(deps, (list, tuple)) and deps:
            deps_text = format_list(deps, max_items=3, max_chars=16)
            if deps_text:
                attrs.append(("Deps", deps_text, "deps"))
    if "meta" in fields:
        meta = raw.get("metadata")
        if isinstance(meta, dict) and meta:
            keys = [key for key in meta.keys() if key not in {"dependencies", "deps"}]
            meta_text = format_list(keys, max_items=max_meta_keys, max_chars=18)
            if meta_text:
                attrs.append(("Meta", meta_text, "meta"))
    return attrs


def summarize_context(raw: Dict[str, Any]) -> str:
    combined = raw.get("context_combined")
    if isinstance(combined, str) and combined.strip():
        return combined.strip()
    sections = raw.get("context_sections")
    if isinstance(sections, list) and sections:
        first = sections[0] if isinstance(sections[0], dict) else None
        if first:
            title = first.get("title") or ""
            content = first.get("content") or ""
            if title and content:
                return f"{title}: {content}"
            return title or content
    return ""


def summarize_context_meta(raw: Dict[str, Any], max_pairs: int = 2) -> str:
    meta = raw.get("context_meta")
    if not isinstance(meta, dict) or not meta:
        return ""
    pairs = []
    for key in list(meta.keys())[:max_pairs]:
        value = meta.get(key)
        if value is None:
            continue
        pairs.append(f"{key}={value}")
    suffix = ""
    if len(meta) > max_pairs:
        suffix = f" +{len(meta) - max_pairs}"
    return ", ".join(pairs) + suffix


DETAIL_LABELS = {
    "instruction": "Instruction",
    "context": "Context",
    "context_sections": "Sections",
    "context_meta": "Context meta",
}


def collect_detail_lines(
    node: PlanNode,
    fields: List[str],
    truncate_details: bool,
    max_chars: int,
) -> List[Tuple[str, List[str]]]:
    raw = node.raw
    lines: List[Tuple[str, List[str]]] = []
    for field in fields:
        label = DETAIL_LABELS.get(field)
        if not label:
            continue
        if field == "instruction":
            text = raw.get("instruction")
            if isinstance(text, str) and text.strip():
                value_lines = wrap_detail_value(
                    text, max_chars, truncate_details
                )
                if value_lines:
                    lines.append((label, value_lines))
        elif field == "context":
            context = summarize_context(raw)
            if context:
                value_lines = wrap_detail_value(
                    context, max_chars, truncate_details
                )
                if value_lines:
                    lines.append((label, value_lines))
        elif field == "context_meta":
            meta = summarize_context_meta(raw)
            if meta:
                value_lines = wrap_detail_value(
                    meta, max_chars, truncate_details
                )
                if value_lines:
                    lines.append((label, value_lines))
        elif field == "context_sections":
            sections = raw.get("context_sections")
            if isinstance(sections, list) and sections:
                titles = [sec.get("title") for sec in sections if isinstance(sec, dict)]
                titles = [title for title in titles if title]
                if titles:
                    joined = (
                        format_list(titles, max_items=2, max_chars=max_chars)
                        if truncate_details
                        else ", ".join(titles)
                    )
                    value_lines = wrap_detail_value(
                        joined, max_chars, truncate_details
                    )
                    if value_lines:
                        lines.append((label, value_lines))
    return lines


def outline_card_height(detail_lines: int) -> float:
    height = OUTLINE_PADDING_Y * 2 + OUTLINE_MAX_LINES * OUTLINE_LINE_HEIGHT
    if detail_lines > 0:
        height += OUTLINE_DETAIL_GAP + detail_lines * OUTLINE_DETAIL_LINE_HEIGHT
    height += OUTLINE_ATTR_GAP + OUTLINE_ATTR_HEIGHT
    return height


def compute_subtree_width(node: PlanNode) -> float:
    if not node.children:
        node.subtree_width = NODE_WIDTH
        return node.subtree_width
    child_widths = [compute_subtree_width(child) for child in node.children]
    children_total = sum(child_widths) + H_GAP * (len(child_widths) - 1)
    node.subtree_width = max(children_total, NODE_WIDTH)
    return node.subtree_width


def assign_layered_positions(node: PlanNode, left: float) -> None:
    if not node.children:
        node.x = left + node.subtree_width / 2
    else:
        child_widths = [child.subtree_width for child in node.children]
        children_total = sum(child_widths) + H_GAP * (len(child_widths) - 1)
        child_left = left + max(0.0, (node.subtree_width - children_total) / 2)
        for child in node.children:
            assign_layered_positions(child, child_left)
            child_left += child.subtree_width + H_GAP
        node.x = left + node.subtree_width / 2
    node.y = node.depth * (NODE_HEIGHT + V_GAP)


def compute_leaf_counts(node: PlanNode) -> int:
    if not node.children:
        node.leaf_count = 1
        return 1
    node.leaf_count = sum(compute_leaf_counts(child) for child in node.children)
    return node.leaf_count


def assign_angles(node: PlanNode, start_angle: float, end_angle: float) -> None:
    node.angle = (start_angle + end_angle) / 2
    if not node.children:
        return
    span = end_angle - start_angle
    current = start_angle
    for child in node.children:
        portion = span * (child.leaf_count / max(node.leaf_count, 1))
        assign_angles(child, current, current + portion)
        current += portion


def layout_layered(root: PlanNode, title_space: int) -> Tuple[int, int]:
    compute_subtree_width(root)
    assign_layered_positions(root, 0.0)
    nodes = list(iter_nodes(root))
    min_x = min(node.x for node in nodes)
    max_x = max(node.x for node in nodes)
    min_y = min(node.y for node in nodes)
    max_y = max(node.y for node in nodes)

    width = (max_x - min_x) + NODE_WIDTH + MARGIN * 2
    height = (max_y - min_y) + NODE_HEIGHT + MARGIN * 2 + title_space
    offset_x = MARGIN - (min_x - NODE_WIDTH / 2)
    offset_y = MARGIN + title_space - (min_y - NODE_HEIGHT / 2)

    for node in nodes:
        node.x += offset_x
        node.y += offset_y

    return math.ceil(width), math.ceil(height)


def layout_radial(
    root: PlanNode, title_space: int
) -> Tuple[int, int, Tuple[float, float], int]:
    assign_depths(root, 0)
    compute_leaf_counts(root)
    assign_angles(root, -math.pi / 2, (3 * math.pi) / 2)

    nodes = list(iter_nodes(root))
    max_depth = max(node.depth for node in nodes)
    max_radius = max_depth * RADIUS_STEP
    diameter = 2 * (max_radius + NODE_WIDTH / 2 + MARGIN)
    width = diameter
    height = diameter + title_space
    center_x = width / 2
    center_y = title_space + diameter / 2

    for node in nodes:
        node.radius = node.depth * RADIUS_STEP
        node.x = center_x + node.radius * math.cos(node.angle)
        node.y = center_y + node.radius * math.sin(node.angle)

    return math.ceil(width), math.ceil(height), (center_x, center_y), max_depth


def estimate_chip_width(label: str, value: str) -> float:
    text_len = len(label) + len(value) + 1
    return ATTR_PADDING_X * 2 + text_len * ATTR_CHAR_WIDTH


def estimate_attr_row_width(attrs: List[Tuple[str, str, str]]) -> float:
    if not attrs:
        return 0.0
    widths = [estimate_chip_width(label, value) for label, value, _ in attrs]
    return sum(widths) + ATTR_GAP * (len(widths) - 1)


def layout_outline(
    root: PlanNode,
    fields: List[str],
    detail_fields: List[str],
    max_meta_keys: int,
    title_space: int,
    truncate_details: bool,
) -> Tuple[int, int, float]:
    assign_depths(root, 0)
    assign_order_codes(root)
    nodes = list(iter_nodes(root))

    max_indent = 0.0
    max_card_width = float(OUTLINE_MIN_WIDTH)
    max_badge_width = 0.0
    max_detail_label_width = 0.0
    if detail_fields:
        max_detail_label_width = max(
            len(DETAIL_LABELS.get(field, "")) * OUTLINE_DETAIL_CHAR_WIDTH
            for field in detail_fields
        )
    for node in nodes:
        badge_width = (
            OUTLINE_BADGE_PADDING_X * 2 + len(node.order_code) * ATTR_CHAR_WIDTH
            if node.order_code
            else 0.0
        )
        max_badge_width = max(max_badge_width, badge_width)
        max_indent = max(max_indent, node.depth * OUTLINE_INDENT)

    for node in nodes:
        node.outline_detail_label_width = max_detail_label_width
        node.outline_badge_width = max_badge_width if node.order_code else 0.0
        badge_space = (
            node.outline_badge_width + OUTLINE_BADGE_GAP if node.order_code else 0.0
        )
        available_label_width = (
            OUTLINE_MAX_WIDTH
            - OUTLINE_STRIPE_WIDTH
            - OUTLINE_PADDING_X * 2
            - badge_space
        )
        max_label_chars = max(12, int(available_label_width / OUTLINE_CHAR_WIDTH))
        max_label_chars = min(max_label_chars, OUTLINE_MAX_CHARS_PER_LINE)
        node.outline_lines = wrap_label(
            node.label, max_label_chars, OUTLINE_MAX_LINES
        )
        detail_max_chars = max(
            18,
            int(
                (
                    OUTLINE_MAX_WIDTH
                    - OUTLINE_STRIPE_WIDTH
                    - OUTLINE_PADDING_X * 2
                    - badge_space
                    - max_detail_label_width
                    - OUTLINE_DETAIL_LABEL_GAP
                )
                / OUTLINE_DETAIL_CHAR_WIDTH
            ),
        )
        node.outline_attrs = collect_attributes(node, fields, max_meta_keys)
        node.outline_details = collect_detail_lines(
            node, detail_fields, truncate_details, detail_max_chars
        )
        node.outline_detail_count = sum(len(lines) for _, lines in node.outline_details)
        node.outline_height = outline_card_height(node.outline_detail_count)
        label_width = 0.0
        if node.outline_lines:
            label_width = (
                max(len(line) for line in node.outline_lines) * OUTLINE_CHAR_WIDTH
            )
        detail_width = 0.0
        if node.outline_details:
            for label, lines in node.outline_details:
                if not lines:
                    continue
                for idx, line in enumerate(lines):
                    value_width = len(line) * OUTLINE_DETAIL_CHAR_WIDTH
                    detail_width = max(
                        detail_width,
                        max_detail_label_width + OUTLINE_DETAIL_LABEL_GAP + value_width,
                    )
        attr_width = estimate_attr_row_width(node.outline_attrs)
        content_width = max(label_width, attr_width, detail_width)
        required_width = (
            OUTLINE_STRIPE_WIDTH + OUTLINE_PADDING_X * 2 + badge_space + content_width
        )
        max_card_width = max(max_card_width, required_width)

    if max_card_width > OUTLINE_MAX_WIDTH:
        max_card_width = OUTLINE_MAX_WIDTH

    total_height = (
        title_space
        + OUTLINE_TOP_MARGIN
        + MARGIN
        + sum(node.outline_height for node in nodes)
        + max(0, len(nodes) - 1) * OUTLINE_GAP
    )
    total_width = MARGIN * 2 + max_indent + max_card_width

    cursor_y = OUTLINE_TOP_MARGIN + title_space
    for node in nodes:
        node.x = MARGIN + node.depth * OUTLINE_INDENT
        node.y = cursor_y + node.outline_height / 2
        cursor_y += node.outline_height + OUTLINE_GAP

    return (math.ceil(total_width), math.ceil(total_height), max_card_width)


def collect_outline_brackets(root: PlanNode) -> List[Tuple[float, float, float]]:
    brackets: List[Tuple[float, float, float]] = []

    def _visit(node: PlanNode) -> None:
        if node.children:
            top = min(child.y - child.outline_height / 2 for child in node.children)
            bottom = max(child.y + child.outline_height / 2 for child in node.children)
            if bottom - top >= OUTLINE_BRACKET_MIN_HEIGHT:
                x = node.x - OUTLINE_BRACKET_OFFSET
                brackets.append((x, top, bottom))
        for child in node.children:
            _visit(child)

    _visit(root)
    return brackets


def svg_style() -> str:
    return f"""
    svg {{
      font-family: {FONT_FAMILY};
      font-variant-numeric: tabular-nums;
      text-rendering: geometricPrecision;
    }}
    .title {{
      font-size: {TITLE_FONT_SIZE}px;
      font-weight: 600;
      fill: #1D3B3A;
    }}
    .edge {{
      stroke: #A6BDBA;
      stroke-width: 1.3;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
    }}
    .halo {{
      stroke: #E3ECEB;
      stroke-width: 1;
      fill: none;
    }}
    .node-card {{
      fill: #EAF4F2;
      stroke: #7CA8A3;
      stroke-width: 1.2;
      filter: url(#cardShadow);
    }}
    .node-card.root {{
      fill: #D9EEE9;
      stroke: #2F6F6B;
      stroke-width: 2;
    }}
    .node-card.virtual {{
      fill: #F2F7F6;
      stroke: #9FB7B4;
      stroke-dasharray: 4 3;
    }}
    .node-label {{
      fill: #1F2F2E;
      font-size: {FONT_SIZE}px;
      font-weight: 500;
      letter-spacing: 0.2px;
    }}
    .outline-card {{
      fill: #F6FBFA;
      stroke: #A6C0BC;
      stroke-width: 1.1;
      filter: url(#cardShadow);
    }}
    .outline-card.root {{
      fill: #E4F2EE;
      stroke: #2F6F6B;
      stroke-width: 1.6;
    }}
    .outline-card.virtual {{
      fill: #F2F7F6;
      stroke: #9FB7B4;
      stroke-dasharray: 4 3;
    }}
    .outline-label {{
      fill: #163331;
      font-size: {OUTLINE_LABEL_SIZE}px;
      font-weight: 600;
      letter-spacing: 0.2px;
    }}
    .outline-badge {{
      fill: #FFFFFF;
      stroke: #7CA8A3;
      stroke-width: 1;
    }}
    .outline-badge-text {{
      fill: #2F6F6B;
      font-size: 10px;
      font-weight: 600;
    }}
    .outline-bracket {{
      stroke: #D2E0DE;
      stroke-width: 1.1;
      fill: none;
      stroke-linecap: round;
      stroke-linejoin: round;
    }}
    .detail-text {{
      font-size: {OUTLINE_DETAIL_FONT_SIZE}px;
      font-weight: 500;
    }}
    .detail-label {{
      font-variant: small-caps;
      font-size: {OUTLINE_DETAIL_FONT_SIZE - 1}px;
      letter-spacing: 0.8px;
      font-weight: 600;
    }}
    .attr-text {{
      font-size: {ATTR_FONT_SIZE}px;
      font-weight: 600;
    }}
    """.strip()


def svg_defs() -> str:
    return """
    <defs>
      <filter id="cardShadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#6A8D89" flood-opacity="0.12" />
      </filter>
      <pattern id="bgDots" width="24" height="24" patternUnits="userSpaceOnUse">
        <circle cx="2" cy="2" r="1.2" fill="#E4EFEE" />
      </pattern>
      <pattern id="bgGrid" width="40" height="40" patternUnits="userSpaceOnUse">
        <path d="M40 0 H0 V40" fill="none" stroke="#EAF2F1" stroke-width="1" />
      </pattern>
    </defs>
    """.strip()


def svg_path_layered(parent: PlanNode, child: PlanNode) -> str:
    px = parent.x
    py = parent.y + NODE_HEIGHT / 2
    cx = child.x
    cy = child.y - NODE_HEIGHT / 2
    mid_y = (py + cy) / 2
    return (
        f"M {px:.1f} {py:.1f} "
        f"C {px:.1f} {mid_y:.1f} {cx:.1f} {mid_y:.1f} {cx:.1f} {cy:.1f}"
    )


def svg_path_radial(
    parent: PlanNode, child: PlanNode, center: Tuple[float, float]
) -> str:
    px = parent.x
    py = parent.y
    cx = child.x
    cy = child.y
    mid_x = (px + cx) / 2
    mid_y = (py + cy) / 2
    dx = mid_x - center[0]
    dy = mid_y - center[1]
    dist = math.hypot(dx, dy) or 1.0
    curve = 22
    cpx = mid_x + dx / dist * curve
    cpy = mid_y + dy / dist * curve
    return f"M {px:.1f} {py:.1f} Q {cpx:.1f} {cpy:.1f} {cx:.1f} {cy:.1f}"


def svg_node(node: PlanNode) -> str:
    rect_x = node.x - NODE_WIDTH / 2
    rect_y = node.y - NODE_HEIGHT / 2
    classes = ["node-card"]
    if node.is_virtual:
        classes.append("virtual")
    elif node.parent_id is None:
        classes.append("root")
    class_attr = " ".join(classes)

    text_start_y = node.y - (len(node.lines) - 1) * LINE_HEIGHT / 2
    lines = "\n".join(
        f'<tspan x="{node.x:.1f}" dy="{0 if i == 0 else LINE_HEIGHT}">{escape(line)}</tspan>'
        for i, line in enumerate(node.lines)
    )
    return (
        f'<g class="node">'
        f'<rect x="{rect_x:.1f}" y="{rect_y:.1f}" width="{NODE_WIDTH}" height="{NODE_HEIGHT}" '
        f'rx="12" ry="12" class="{class_attr}" />'
        f'<text x="{node.x:.1f}" y="{text_start_y:.1f}" text-anchor="middle" class="node-label">'
        f"{lines}</text></g>"
    )


def svg_node_outline(node: PlanNode, card_width: float) -> str:
    rect_x = node.x
    rect_y = node.y - node.outline_height / 2
    classes = ["outline-card"]
    if node.is_virtual:
        classes.append("virtual")
    elif node.parent_id is None:
        classes.append("root")
    class_attr = " ".join(classes)

    stripe_color = DEPTH_COLORS[node.depth % len(DEPTH_COLORS)]
    badge_width = node.outline_badge_width
    badge_x = rect_x + OUTLINE_STRIPE_WIDTH + OUTLINE_PADDING_X
    badge_y = rect_y + OUTLINE_PADDING_Y
    label_x = badge_x + (badge_width + OUTLINE_BADGE_GAP if node.order_code else 0.0)
    label_y = rect_y + OUTLINE_PADDING_Y + OUTLINE_LABEL_SIZE

    label_lines = node.outline_lines or ["Untitled task"]
    label_spans = "\n".join(
        f'<tspan x="{label_x:.1f}" dy="{0 if i == 0 else OUTLINE_LINE_HEIGHT}">{escape(line)}</tspan>'
        for i, line in enumerate(label_lines)
    )

    detail_block = 0.0
    if node.outline_detail_count > 0:
        detail_block = (
            OUTLINE_DETAIL_GAP + node.outline_detail_count * OUTLINE_DETAIL_LINE_HEIGHT
        )
    chip_y = (
        rect_y
        + OUTLINE_PADDING_Y
        + OUTLINE_MAX_LINES * OUTLINE_LINE_HEIGHT
        + detail_block
        + OUTLINE_ATTR_GAP
    )
    chip_x = label_x
    chips: List[str] = []
    for label, value, key in node.outline_attrs:
        color = ATTRIBUTE_COLORS.get(key, "#7CA8A3")
        fill = lighten_hex(color, 0.84)
        chip_width = estimate_chip_width(label, value)
        chips.append(
            f'<rect x="{chip_x:.1f}" y="{chip_y:.1f}" width="{chip_width:.1f}" '
            f'height="{OUTLINE_ATTR_HEIGHT}" rx="8" ry="8" '
            f'style="fill:{fill};stroke:{color};stroke-width:1" />'
        )
        text_y = chip_y + ATTR_FONT_SIZE + 4
        chips.append(
            f'<text x="{chip_x + ATTR_PADDING_X:.1f}" y="{text_y:.1f}" class="attr-text">'
            f'<tspan fill="{color}">{escape(label)}</tspan>'
            f'<tspan fill="#1F2F2E">: {escape(value)}</tspan>'
            f"</text>"
        )
        chip_x += chip_width + ATTR_GAP

    badge_svg = ""
    if node.order_code:
        badge_svg = (
            f'<rect x="{badge_x:.1f}" y="{badge_y:.1f}" width="{badge_width:.1f}" '
            f'height="{OUTLINE_BADGE_HEIGHT}" rx="8" ry="8" class="outline-badge" />'
            f'<text x="{badge_x + badge_width / 2:.1f}" y="{badge_y + 12:.1f}" '
            f'text-anchor="middle" class="outline-badge-text">{escape(node.order_code)}</text>'
        )

    detail_svg = ""
    if node.outline_detail_count > 0:
        detail_start_y = (
            rect_y
            + OUTLINE_PADDING_Y
            + OUTLINE_MAX_LINES * OUTLINE_LINE_HEIGHT
            + OUTLINE_DETAIL_GAP
            + OUTLINE_DETAIL_FONT_SIZE
        )
        detail_text = []
        line_index = 0
        label_color = ATTRIBUTE_COLORS.get("meta", "#6E8F8C")
        value_x = label_x + node.outline_detail_label_width + OUTLINE_DETAIL_LABEL_GAP
        for label, lines in node.outline_details:
            if not lines:
                continue
            for idx, line in enumerate(lines):
                line_y = detail_start_y + line_index * OUTLINE_DETAIL_LINE_HEIGHT
                if idx == 0:
                    detail_text.append(
                        f'<text x="{label_x:.1f}" y="{line_y:.1f}" class="detail-text">'
                        f'<tspan class="detail-label" fill="{label_color}">{escape(label)}:</tspan>'
                        f"</text>"
                    )
                    detail_text.append(
                        f'<text x="{value_x:.1f}" y="{line_y:.1f}" class="detail-text">'
                        f'<tspan fill="#3C4B4A">{escape(line)}</tspan>'
                        f"</text>"
                    )
                else:
                    detail_text.append(
                        f'<text x="{value_x:.1f}" y="{line_y:.1f}" class="detail-text">'
                        f'<tspan fill="#3C4B4A">{escape(line)}</tspan>'
                        f"</text>"
                    )
                line_index += 1
        detail_svg = "".join(detail_text)

    return (
        f'<g class="outline-node">'
        f'<rect x="{rect_x:.1f}" y="{rect_y:.1f}" width="{card_width:.1f}" '
        f'height="{node.outline_height:.1f}" rx="14" ry="14" class="{class_attr}" />'
        f'<rect x="{rect_x:.1f}" y="{rect_y:.1f}" width="{OUTLINE_STRIPE_WIDTH}" '
        f'height="{node.outline_height:.1f}" rx="8" ry="8" style="fill:{stripe_color}" />'
        f"{badge_svg}"
        f'<text x="{label_x:.1f}" y="{label_y:.1f}" class="outline-label">'
        f"{label_spans}</text>"
        f"{detail_svg}"
        f"{''.join(chips)}"
        f"</g>"
    )


def render_svg(
    root: PlanNode,
    title: str,
    layout: str,
    output: Path,
    show_title: bool,
    transparent: bool,
    outline_fields: List[str],
    detail_fields: List[str],
    max_meta_keys: int,
    pattern: str,
    outline_timeline: bool,
    truncate_details: bool,
) -> None:
    assign_depths(root, 0)
    edges = [(node, child) for node in iter_nodes(root) for child in node.children]
    title_space = TITLE_HEIGHT if show_title else 0

    if layout == "layered":
        width, height = layout_layered(root, title_space)
        center = None
        max_depth = 0
        outline_card_width = 0.0
        outline_card_height = 0.0
        outline_detail_lines = 0
    else:
        if layout == "radial":
            width, height, center, max_depth = layout_radial(root, title_space)
            outline_card_width = 0.0
            outline_card_height = 0.0
            outline_detail_lines = 0
        else:
            width, height, outline_card_width = layout_outline(
                root,
                outline_fields,
                detail_fields,
                max_meta_keys,
                title_space,
                truncate_details,
            )
            center = None
            max_depth = 0

    lines: List[str] = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
    )
    lines.append(svg_defs())
    lines.append(f"<style>{svg_style()}</style>")
    if not transparent:
        lines.append('<rect width="100%" height="100%" fill="white" />')
        if pattern != "none":
            pattern_id = "bgDots" if pattern == "dots" else "bgGrid"
            lines.append(
                f'<rect width="100%" height="100%" fill="url(#{pattern_id})" opacity="0.45" />'
            )

    if show_title:
        title_text = escape(title)
        title_y = max(TITLE_FONT_SIZE + 6, title_space - 4)
        if layout == "radial":
            lines.append(
                f'<text class="title" x="{width / 2:.1f}" y="{title_y:.1f}" text-anchor="middle">{title_text}</text>'
            )
        else:
            lines.append(
                f'<text class="title" x="{MARGIN:.1f}" y="{title_y:.1f}" text-anchor="start">{title_text}</text>'
            )

    if layout == "radial" and center is not None and max_depth > 0:
        for depth in range(1, max_depth + 1):
            radius = depth * RADIUS_STEP
            lines.append(
                f'<circle class="halo" cx="{center[0]:.1f}" cy="{center[1]:.1f}" r="{radius:.1f}" />'
            )

    if layout == "outline":
        brackets = collect_outline_brackets(root)
        if brackets:
            lines.append('<g class="outline-brackets">')
            for x, top, bottom in brackets:
                radius = OUTLINE_BRACKET_RADIUS
                lines.append(
                    f'<path class="outline-bracket" d="M {x + OUTLINE_BRACKET_WIDTH:.1f} {top:.1f} '
                    f'Q {x:.1f} {top:.1f} {x:.1f} {top + radius:.1f} '
                    f'L {x:.1f} {bottom - radius:.1f} '
                    f'Q {x:.1f} {bottom:.1f} {x + OUTLINE_BRACKET_WIDTH:.1f} {bottom:.1f}" />'
                )
            lines.append("</g>")

    if layout != "outline":
        lines.append('<g class="edges">')
        for parent, child in edges:
            if layout == "layered":
                path = svg_path_layered(parent, child)
            else:
                path = svg_path_radial(parent, child, center or (0.0, 0.0))
            lines.append(f'<path class="edge" d="{path}" />')
        lines.append("</g>")

    nodes = list(iter_nodes(root))
    if layout == "outline" and outline_timeline and nodes:
        timeline_x = MARGIN - 18
        top_y = nodes[0].y - nodes[0].outline_height / 2 + 8
        bottom_y = nodes[-1].y + nodes[-1].outline_height / 2 - 8
        lines.append('<g class="outline-timeline">')
        lines.append(
            f'<line x1="{timeline_x:.1f}" y1="{top_y:.1f}" x2="{timeline_x:.1f}" y2="{bottom_y:.1f}" '
            f'stroke="#C6D8D5" stroke-width="1.2" />'
        )
        for node in nodes:
            lines.append(
                f'<circle cx="{timeline_x:.1f}" cy="{node.y:.1f}" r="4" '
                f'fill="#FFFFFF" stroke="#7CA8A3" stroke-width="1.2" />'
            )
        lines.append("</g>")

    lines.append('<g class="nodes">')
    for node in nodes:
        if layout == "outline":
            lines.append(svg_node_outline(node, outline_card_width))
        else:
            lines.append(svg_node(node))
    lines.append("</g>")

    lines.append("</svg>")
    output.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    data = json.loads(args.input.read_text(encoding="utf-8"))
    nodes, title = load_plan_nodes(data)
    roots = [node for node in nodes.values() if node.parent_id not in nodes]
    if not roots:
        raise ValueError("No root nodes found in plan.")

    _filtered_nodes, filtered_roots = filter_nodes(
        nodes,
        roots,
        args.node_id,
        not args.exclude_children,
        args.max_depth,
    )

    root = ensure_single_root(filtered_roots, title)
    render_title = title
    if args.node_id is not None:
        render_title = f"{title} (node {args.node_id})"

    output = args.output
    if output is None:
        output = args.input.with_name(f"{args.input.stem}_{args.layout}.svg")

    outline_fields = parse_fields(args.show_fields)
    detail_fields = parse_detail_fields(args.detail_fields)

    render_svg(
        root=root,
        title=render_title,
        layout=args.layout,
        output=output,
        show_title=not args.hide_title,
        transparent=args.transparent,
        outline_fields=outline_fields,
        detail_fields=detail_fields,
        max_meta_keys=args.max_meta_keys,
        pattern=args.pattern,
        outline_timeline=args.outline_timeline,
        truncate_details=args.truncate_details,
    )
    print(f"[OK] Wrote SVG to {output}")


if __name__ == "__main__":
    main()
