"""
Mod Conflict Graph View for RimModManager
Interactive visualization of mod dependencies and conflicts.
"""

import logging
import math
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsTextItem,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QDialog, QDialogButtonBox,
    QToolTip
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QLineF, pyqtSignal
from PyQt6.QtGui import (
    QPen, QBrush, QColor, QPainter, QFont, QWheelEvent,
    QPainterPath
)

log = logging.getLogger("rimmodmanager.ui.graph_view")


class EdgeType(Enum):
    """Types of edges in the dependency graph."""
    DEPENDENCY = "dependency"      # Green - satisfied dependency
    MISSING = "missing"            # Yellow - missing dependency
    CONFLICT = "conflict"          # Red - incompatible
    LOAD_ORDER = "load_order"      # Blue - load order issue


@dataclass
class GraphNode:
    """Data for a node in the graph."""
    mod_id: str
    name: str
    x: float = 0
    y: float = 0
    is_active: bool = True
    has_issues: bool = False


@dataclass  
class GraphEdge:
    """Data for an edge in the graph."""
    source_id: str
    target_id: str
    edge_type: EdgeType
    label: str = ""


# Color scheme
COLORS = {
    EdgeType.DEPENDENCY: QColor("#69db7c"),   # Green
    EdgeType.MISSING: QColor("#ffd43b"),      # Yellow
    EdgeType.CONFLICT: QColor("#ff6b6b"),     # Red
    EdgeType.LOAD_ORDER: QColor("#74c0fc"),   # Blue
}

NODE_COLORS = {
    "normal": QColor("#4a4a4a"),
    "active": QColor("#2d5a2d"),
    "issue": QColor("#5a2d2d"),
    "selected": QColor("#3d5a8a"),
}


class ModNode(QGraphicsEllipseItem):
    """A draggable node representing a mod."""
    
    def __init__(self, data: GraphNode, radius: float = 25):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.data = data
        self.radius = radius
        self.edges: list['ModEdge'] = []
        
        # Visual setup
        self._setup_appearance()
        
        # Enable interactions
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setZValue(1)  # Above edges
        
        # Label
        self._label = QGraphicsTextItem(self)
        self._label.setPlainText(self._truncate_name(data.name))
        self._label.setDefaultTextColor(QColor("#ffffff"))
        font = QFont("Sans", 8)
        self._label.setFont(font)
        
        # Center label below node
        label_rect = self._label.boundingRect()
        self._label.setPos(-label_rect.width() / 2, radius + 2)
        
        # Set position
        self.setPos(data.x, data.y)
    
    def _truncate_name(self, name: str, max_len: int = 15) -> str:
        """Truncate name for display."""
        if len(name) <= max_len:
            return name
        return name[:max_len-2] + "..."
    
    def _setup_appearance(self):
        """Set up node colors based on state."""
        if self.data.has_issues:
            color = NODE_COLORS["issue"]
        elif self.data.is_active:
            color = NODE_COLORS["active"]
        else:
            color = NODE_COLORS["normal"]
        
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor("#888888"), 2))
    
    def add_edge(self, edge: 'ModEdge'):
        """Add an edge connected to this node."""
        self.edges.append(edge)
    
    def itemChange(self, change, value):
        """Handle position changes to update edges."""
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:
                edge.adjust()
            # Update data
            self.data.x = self.pos().x()
            self.data.y = self.pos().y()
        return super().itemChange(change, value)
    
    def hoverEnterEvent(self, event):
        """Show tooltip on hover."""
        self.setPen(QPen(QColor("#ffffff"), 3))
        # PyQt6: screenPos() returns QPointF, use toPoint() on QPointF
        screen_pos = event.screenPos()
        if hasattr(screen_pos, 'toPoint'):
            screen_pos = screen_pos.toPoint()
        QToolTip.showText(
            screen_pos,
            f"{self.data.name}\n{self.data.mod_id}"
        )
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        """Reset appearance on hover leave."""
        self.setPen(QPen(QColor("#888888"), 2))
        super().hoverLeaveEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Emit signal on double click."""
        scene = self.scene()
        if scene and hasattr(scene, 'node_double_clicked'):
            scene.node_double_clicked.emit(self.data.mod_id)
        super().mouseDoubleClickEvent(event)


class ModEdge(QGraphicsLineItem):
    """An edge representing a dependency or conflict."""
    
    def __init__(self, source: ModNode, target: ModNode, edge_type: EdgeType, label: str = ""):
        super().__init__()
        self.source = source
        self.target = target
        self.edge_type = edge_type
        self.label_text = label
        
        # Visual setup
        color = COLORS.get(edge_type, QColor("#888888"))
        pen = QPen(color, 2)
        
        if edge_type == EdgeType.MISSING:
            pen.setStyle(Qt.PenStyle.DashLine)
        elif edge_type == EdgeType.CONFLICT:
            pen.setWidth(3)
        
        self.setPen(pen)
        self.setZValue(0)  # Below nodes
        
        # Arrow head
        self._arrow_size = 10
        
        # Register with nodes
        source.add_edge(self)
        target.add_edge(self)
        
        # Initial position
        self.adjust()
    
    def adjust(self):
        """Update edge position based on node positions."""
        if not self.source or not self.target:
            return
        
        line = QLineF(
            self.source.pos(),
            self.target.pos()
        )
        
        # Shorten line to not overlap with nodes
        length = line.length()
        if length < 1:
            return
        
        # Calculate offset for node radius
        offset = QPointF(
            (line.dx() * self.source.radius) / length,
            (line.dy() * self.source.radius) / length
        )
        
        start = line.p1() + offset
        end = line.p2() - offset
        
        self.setLine(QLineF(start, end))
    
    def paint(self, painter: QPainter, option, widget):
        """Draw edge with arrow head."""
        if not self.source or not self.target:
            return
        
        line = self.line()
        if line.length() < 1:
            return
        
        # Draw line
        painter.setPen(self.pen())
        painter.drawLine(line)
        
        # Draw arrow head at target
        angle = math.atan2(-line.dy(), line.dx())
        
        arrow_p1 = line.p2() - QPointF(
            math.sin(angle + math.pi / 3) * self._arrow_size,
            math.cos(angle + math.pi / 3) * self._arrow_size
        )
        arrow_p2 = line.p2() - QPointF(
            math.sin(angle + math.pi - math.pi / 3) * self._arrow_size,
            math.cos(angle + math.pi - math.pi / 3) * self._arrow_size
        )
        
        # Draw arrow
        arrow_path = QPainterPath()
        arrow_path.moveTo(line.p2())
        arrow_path.lineTo(arrow_p1)
        arrow_path.lineTo(arrow_p2)
        arrow_path.closeSubpath()
        
        painter.setBrush(self.pen().color())
        painter.drawPath(arrow_path)
    
    def boundingRect(self) -> QRectF:
        """Return bounding rect including arrow."""
        extra = self._arrow_size + self.pen().width()
        line = self.line()
        return QRectF(line.p1(), line.p2()).normalized().adjusted(
            -extra, -extra, extra, extra
        )


class ModGraphScene(QGraphicsScene):
    """Scene for the mod dependency graph."""
    
    node_double_clicked = pyqtSignal(str)  # mod_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.nodes: dict[str, ModNode] = {}
        self.edges: list[ModEdge] = []
        self.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
    
    def clear_graph(self):
        """Clear all nodes and edges."""
        self.clear()
        self.nodes.clear()
        self.edges.clear()
    
    def add_node(self, data: GraphNode) -> ModNode:
        """Add a node to the graph."""
        node = ModNode(data)
        self.addItem(node)
        self.nodes[data.mod_id] = node
        return node
    
    def add_edge(self, source_id: str, target_id: str, edge_type: EdgeType, label: str = "") -> Optional[ModEdge]:
        """Add an edge between two nodes."""
        source = self.nodes.get(source_id)
        target = self.nodes.get(target_id)
        
        if not source or not target:
            return None
        
        edge = ModEdge(source, target, edge_type, label)
        self.addItem(edge)
        self.edges.append(edge)
        return edge
    
    def layout_circular(self):
        """Arrange nodes in a circle."""
        if not self.nodes:
            return
        
        count = len(self.nodes)
        radius = max(150, count * 20)
        
        for i, node in enumerate(self.nodes.values()):
            angle = 2 * math.pi * i / count
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            node.setPos(x, y)
    
    def layout_hierarchical(self):
        """Arrange nodes in hierarchical layers based on dependencies."""
        if not self.nodes:
            return
        
        # Calculate node levels based on dependencies
        levels: dict[str, int] = {}
        
        # Find root nodes (no incoming edges)
        incoming: dict[str, int] = {mod_id: 0 for mod_id in self.nodes}
        for edge in self.edges:
            if edge.target.data.mod_id in incoming:
                incoming[edge.target.data.mod_id] += 1
        
        # BFS to assign levels
        current_level = 0
        current_nodes = [mod_id for mod_id, count in incoming.items() if count == 0]
        
        if not current_nodes:
            # No roots, use all nodes
            current_nodes = list(self.nodes.keys())
        
        while current_nodes:
            for mod_id in current_nodes:
                levels[mod_id] = current_level
            
            # Find next level
            next_nodes = []
            for edge in self.edges:
                source_id = edge.source.data.mod_id
                target_id = edge.target.data.mod_id
                if source_id in current_nodes and target_id not in levels:
                    next_nodes.append(target_id)
            
            current_nodes = list(set(next_nodes))
            current_level += 1
            
            # Safety limit
            if current_level > 50:
                break
        
        # Assign remaining nodes
        for mod_id in self.nodes:
            if mod_id not in levels:
                levels[mod_id] = current_level
        
        # Group by level
        level_groups: dict[int, list[str]] = {}
        for mod_id, level in levels.items():
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(mod_id)
        
        # Position nodes
        y_spacing = 100
        x_spacing = 120
        
        for level, mod_ids in level_groups.items():
            y = level * y_spacing
            total_width = (len(mod_ids) - 1) * x_spacing
            start_x = -total_width / 2
            
            for i, mod_id in enumerate(mod_ids):
                x = start_x + i * x_spacing
                self.nodes[mod_id].setPos(x, y)


class ModGraphView(QGraphicsView):
    """Interactive view for the mod dependency graph."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = ModGraphScene(self)
        self.setScene(self._scene)
        
        # View settings
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        # Zoom limits
        self._zoom = 1.0
        self._zoom_min = 0.1
        self._zoom_max = 3.0
    
    @property
    def graph_scene(self) -> ModGraphScene:
        return self._scene
    
    def wheelEvent(self, event: QWheelEvent):
        """Handle zoom with mouse wheel."""
        factor = 1.15
        
        if event.angleDelta().y() > 0:
            # Zoom in
            if self._zoom < self._zoom_max:
                self._zoom *= factor
                self.scale(factor, factor)
        else:
            # Zoom out
            if self._zoom > self._zoom_min:
                self._zoom /= factor
                self.scale(1 / factor, 1 / factor)
    
    def fit_to_view(self):
        """Fit all content in view."""
        self.fitInView(self._scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()
    
    def reset_zoom(self):
        """Reset zoom to 100%."""
        self.resetTransform()
        self._zoom = 1.0


class ConflictGraphDialog(QDialog):
    """Dialog showing mod conflict/dependency graph."""
    
    mod_selected = pyqtSignal(str)  # mod_id
    
    def __init__(self, mods: list, parent=None):
        super().__init__(parent)
        self.mods = mods
        self.setWindowTitle("🔗 Mod Dependency Graph")
        self.setMinimumSize(900, 600)
        
        self._setup_ui()
        self._build_graph()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        # Layout selector
        toolbar.addWidget(QLabel("Layout:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["Hierarchical", "Circular"])
        self.layout_combo.currentTextChanged.connect(self._on_layout_changed)
        toolbar.addWidget(self.layout_combo)
        
        toolbar.addSpacing(20)
        
        # Filter
        toolbar.addWidget(QLabel("Show:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Connections", "Conflicts Only", "Missing Only", "Active Mods Only"])
        self.filter_combo.currentTextChanged.connect(self._rebuild_graph)
        toolbar.addWidget(self.filter_combo)
        
        toolbar.addStretch()
        
        # Zoom controls
        btn_fit = QPushButton("Fit")
        btn_fit.clicked.connect(lambda: self.graph_view.fit_to_view())
        toolbar.addWidget(btn_fit)
        
        btn_reset = QPushButton("100%")
        btn_reset.clicked.connect(lambda: self.graph_view.reset_zoom())
        toolbar.addWidget(btn_reset)
        
        layout.addLayout(toolbar)
        
        # Graph view
        self.graph_view = ModGraphView()
        self.graph_view.graph_scene.node_double_clicked.connect(self._on_node_clicked)
        layout.addWidget(self.graph_view, 1)
        
        # Legend
        legend = QHBoxLayout()
        legend.addWidget(self._create_legend_item("Dependency", COLORS[EdgeType.DEPENDENCY]))
        legend.addWidget(self._create_legend_item("Missing", COLORS[EdgeType.MISSING]))
        legend.addWidget(self._create_legend_item("Conflict", COLORS[EdgeType.CONFLICT]))
        legend.addWidget(self._create_legend_item("Load Order", COLORS[EdgeType.LOAD_ORDER]))
        legend.addStretch()
        layout.addLayout(legend)
        
        # Stats
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #888;")
        layout.addWidget(self.stats_label)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _create_legend_item(self, text: str, color: QColor) -> QWidget:
        """Create a legend item widget."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 10, 0)
        
        # Color box
        color_label = QLabel("━━")
        color_label.setStyleSheet(f"color: {color.name()};")
        layout.addWidget(color_label)
        
        # Text
        layout.addWidget(QLabel(text))
        
        return widget
    
    def _build_graph(self):
        """Build the graph from mod data."""
        self._rebuild_graph()
    
    def _rebuild_graph(self):
        """Rebuild graph with current filter."""
        scene = self.graph_view.graph_scene
        scene.clear_graph()
        
        filter_mode = self.filter_combo.currentText()
        
        # Build mod lookup
        mod_by_id = {mod.package_id.lower(): mod for mod in self.mods}
        
        # Determine which mods to show
        mods_to_show = set()
        edges_to_add = []
        
        for mod in self.mods:
            mod_id = mod.package_id.lower()
            has_issues = False
            
            # Check dependencies
            for dep in getattr(mod, 'dependencies', []):
                dep_id = dep.lower()
                if dep_id in mod_by_id:
                    edges_to_add.append((dep_id, mod_id, EdgeType.DEPENDENCY, "depends"))
                    mods_to_show.add(mod_id)
                    mods_to_show.add(dep_id)
                else:
                    # Missing dependency
                    has_issues = True
                    if filter_mode in ["All Connections", "Missing Only"]:
                        edges_to_add.append((f"missing:{dep_id}", mod_id, EdgeType.MISSING, "missing"))
                        mods_to_show.add(mod_id)
            
            # Check incompatibilities
            for incompat in getattr(mod, 'incompatible_with', []):
                incompat_id = incompat.lower()
                if incompat_id in mod_by_id:
                    has_issues = True
                    if filter_mode in ["All Connections", "Conflicts Only"]:
                        edges_to_add.append((mod_id, incompat_id, EdgeType.CONFLICT, "conflict"))
                        mods_to_show.add(mod_id)
                        mods_to_show.add(incompat_id)
            
            # Check load order
            for load_after in getattr(mod, 'load_after', []):
                after_id = load_after.lower()
                if after_id in mod_by_id:
                    if filter_mode == "All Connections":
                        edges_to_add.append((after_id, mod_id, EdgeType.LOAD_ORDER, "loadAfter"))
                        mods_to_show.add(mod_id)
                        mods_to_show.add(after_id)
        
        # Filter by active mods if needed
        if filter_mode == "Active Mods Only":
            active_ids = {mod.package_id.lower() for mod in self.mods if getattr(mod, 'is_active', True)}
            mods_to_show = mods_to_show.intersection(active_ids)
        
        # If no connections, show all mods with issues
        if not mods_to_show:
            mods_to_show = {mod.package_id.lower() for mod in self.mods[:50]}  # Limit to 50
        
        # Add nodes
        for mod in self.mods:
            mod_id = mod.package_id.lower()
            if mod_id in mods_to_show:
                has_issues = any(
                    e[1] == mod_id and e[2] in [EdgeType.MISSING, EdgeType.CONFLICT]
                    for e in edges_to_add
                )
                node_data = GraphNode(
                    mod_id=mod_id,
                    name=mod.name,
                    is_active=getattr(mod, 'is_active', True),
                    has_issues=has_issues
                )
                scene.add_node(node_data)
        
        # Add placeholder nodes for missing deps
        for edge in edges_to_add:
            if edge[0].startswith("missing:"):
                missing_id = edge[0]
                if missing_id not in scene.nodes:
                    node_data = GraphNode(
                        mod_id=missing_id,
                        name=f"❓ {edge[0][8:]}",
                        is_active=False,
                        has_issues=True
                    )
                    scene.add_node(node_data)
        
        # Add edges
        for source, target, edge_type, label in edges_to_add:
            if source in scene.nodes and target in scene.nodes:
                scene.add_edge(source, target, edge_type, label)
        
        # Apply layout
        self._apply_layout()
        
        # Update stats
        self.stats_label.setText(
            f"Nodes: {len(scene.nodes)} | Edges: {len(scene.edges)}"
        )
        
        # Fit view
        self.graph_view.fit_to_view()
    
    def _apply_layout(self):
        """Apply current layout algorithm."""
        layout_name = self.layout_combo.currentText()
        scene = self.graph_view.graph_scene
        
        if layout_name == "Circular":
            scene.layout_circular()
        else:
            scene.layout_hierarchical()
    
    def _on_layout_changed(self, layout_name: str):
        """Handle layout change."""
        self._apply_layout()
        self.graph_view.fit_to_view()
    
    def _on_node_clicked(self, mod_id: str):
        """Handle node double-click."""
        if not mod_id.startswith("missing:"):
            self.mod_selected.emit(mod_id)
