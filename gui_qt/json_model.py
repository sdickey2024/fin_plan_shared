from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Union, Dict

from PySide6.QtCore import Qt, QAbstractItemModel, QModelIndex


def _type_name(v: Any) -> str:
    if isinstance(v, dict):
        return "object"
    if isinstance(v, list):
        return "array"
    if isinstance(v, bool):
        return "bool"
    if v is None:
        return "null"
    if isinstance(v, (int, float)):
        return "number"
    return "string"


def _is_scalar(v: Any) -> bool:
    return not isinstance(v, (dict, list))


def _format_value(v: Any) -> str:
    if isinstance(v, (dict, list)):
        return ""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _parse_typed(text: str) -> Any:
    s = text.strip()
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if s.lower() == "null":
        return None

    # number?
    try:
        # Keep ints as ints when possible
        if any(c in s.lower() for c in [".", "e"]):
            return float(s)
        return int(s)
    except Exception:
        pass

    # object/array?
    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
        try:
            import json
            return json.loads(s)
        except Exception:
            # fall through
            pass

    return s


@dataclass
class JsonNode:
    key: str
    value: Any
    parent: Optional["JsonNode"] = None
    children: List["JsonNode"] = None

    def __post_init__(self):
        self.children = []
        self.rebuild_children()

    def rebuild_children(self):
        self.children = []
        v = self.value
        if isinstance(v, dict):
            for k, child_v in v.items():
                self.children.append(JsonNode(str(k), child_v, self))
        elif isinstance(v, list):
            for i, child_v in enumerate(v):
                label = f"[{i}]"
                if isinstance(child_v, dict) and "event" in child_v:
                    label += f" {child_v.get('event')}"
                self.children.append(JsonNode(label, child_v, self))

    def child(self, row: int) -> "JsonNode":
        return self.children[row]

    def row(self) -> int:
        if not self.parent:
            return 0
        return self.parent.children.index(self)


class JsonModel(QAbstractItemModel):
    """
    Columns:
      0: Key / Index
      1: Type
      2: Value (editable for scalar nodes)
    """
    def __init__(self, data: Any):
        super().__init__()
        self.root = JsonNode("root", data)
        self._dirty = False

    def isDirty(self) -> bool:
        return self._dirty

    def setClean(self):
        self._dirty = False

    def markDirty(self):
        self._dirty = True

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 3

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        node = self._node(parent)
        return len(node.children)

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        node = self._node(parent)
        if row < 0 or row >= len(node.children):
            return QModelIndex()
        return self.createIndex(row, column, node.children[row])

    def parent(self, index: QModelIndex) -> QModelIndex:
        node = self._node(index)
        if not node or not node.parent or node.parent == self.root:
            return QModelIndex()
        return self.createIndex(node.parent.row(), 0, node.parent)

    def _node(self, index: QModelIndex) -> JsonNode:
        if index.isValid():
            return index.internalPointer()
        return self.root

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        node = self._node(index)

        if role in (Qt.DisplayRole, Qt.EditRole):
            if index.column() == 0:
                return node.key
            if index.column() == 1:
                return _type_name(node.value)
            if index.column() == 2:
                return _format_value(node.value)

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if role != Qt.EditRole or not index.isValid():
            return False
        node = self._node(index)
        if index.column() != 2:
            return False
        if not _is_scalar(node.value):
            return False

        try:
            new_val = _parse_typed(str(value))
            node.value = new_val
            # Ensure parent container reflects the edit
            self._writeback_to_parent(node)
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            # Type column changes too
            type_idx = self.index(index.row(), 1, index.parent())
            self.dataChanged.emit(type_idx, type_idx, [Qt.DisplayRole])
            self._dirty = True
            return True
        except Exception:
            return False

    def _writeback_to_parent(self, node: JsonNode):
        if not node.parent:
            return
        p = node.parent
        if isinstance(p.value, dict):
            # Keys in dict nodes are stored as strings; keep as-is
            p.value[node.key] = node.value
        elif isinstance(p.value, list):
            # find list index from label "[i]"
            import re
            m = re.match(r"\[(\d+)\]", node.key)
            if m:
                i = int(m.group(1))
                if 0 <= i < len(p.value):
                    p.value[i] = node.value

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        node = self._node(index)
        base = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if index.column() == 2 and _is_scalar(node.value):
            return base | Qt.ItemIsEditable
        return base

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return ["Key", "Type", "Value"][section]
        return None

    def toObject(self) -> Any:
        return self._node_to_value(self.root)

    def _node_to_value(self, node: JsonNode) -> Any:
        # Leaf
        if not node.children:
            return node.value

        if isinstance(node.value, list):
            return [self._node_to_value(c) for c in node.children]

        if isinstance(node.value, dict):
            # Children keys include list labels; for dict nodes, they're real keys
            out: Dict[str, Any] = {}
            for c in node.children:
                out[c.key] = self._node_to_value(c)
            return out

        # Shouldn't happen, but safe fallback
        return node.value

    def resetData(self, data: Any):
        self.beginResetModel()
        self.root = JsonNode("root", data)
        self._dirty = False
        self.endResetModel()
