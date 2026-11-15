"""Vector symbols and theme-aware presentation for the approved A2 workbench."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QAction
from appearance import colours


def icon(name, colour='#17335a'):
    """Draw local vector symbols; labels remain the accessible command names."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(64 / 24, 64 / 24)
    painter.setPen(QPen(QColor(colour), 1.65, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)

    def path(points, close=False):
        p = QPainterPath(QPointF(*points[0]))
        for point in points[1:]:
            p.lineTo(*point)
        if close:
            p.closeSubpath()
        painter.drawPath(p)

    def rect(x, y, w, h):
        painter.drawRoundedRect(QRectF(x, y, w, h), 1, 1)

    def circle(x, y, radius):
        painter.drawEllipse(QPointF(x, y), radius, radius)

    if name == 'save':
        path([(4, 3), (18, 3), (21, 6), (21, 21), (3, 21), (3, 3)], True)
        rect(7, 3, 9, 6)
        rect(7, 14, 10, 7)
    elif name in ('undo', 'redo'):
        if name == 'redo':
            painter.translate(24, 0)
            painter.scale(-1, 1)
        path([(8, 4), (3, 9), (8, 14)])
        p = QPainterPath(QPointF(3, 9))
        p.cubicTo(20, 5, 24, 20, 12, 20)
        painter.drawPath(p)
    elif name == 'select':
        path([(5, 2), (19, 13), (12, 14), (9, 21)], True)
        path([(12, 14), (16, 21)])
    elif name == 'corridor':
        path([(4, 19), (10, 12), (16, 12), (21, 4)])
        for x, y in ((4, 19), (10, 12), (16, 12), (21, 4)):
            circle(x, y, 1.5)
    elif name == 'edge':
        path([(5, 18), (19, 6)])
        circle(5, 18, 2.5)
        circle(19, 6, 2.5)
    elif name == 'node':
        circle(12, 12, 5)
        circle(12, 12, 1)
        for pts in ([(12, 2), (12, 5)], [(12, 19), (12, 22)], [(2, 12), (5, 12)], [(19, 12), (22, 12)]):
            path(pts)
    elif name == 'transition':
        path([(3, 4), (21, 4)])
        path([(3, 20), (21, 20)])
        path([(12, 4), (12, 8)])
        path([(12, 16), (12, 20)])
        path([(12, 8), (16, 12), (12, 16), (8, 12)], True)
    elif name == 'lift':
        rect(3, 7, 18, 15)
        path([(12, 9), (12, 20)])
        path([(6, 5), (6, 1), (4, 3)])
        path([(6, 1), (8, 3)])
        path([(18, 1), (18, 5), (16, 3)])
        path([(18, 5), (20, 3)])
    elif name == 'location':
        p = QPainterPath(QPointF(12, 22))
        p.cubicTo(-6, 5, 6, 2, 12, 2)
        p.cubicTo(24, 2, 23, 10, 12, 22)
        painter.drawPath(p)
        circle(12, 8, 2.4)
    elif name == 'door':
        path([(4, 22), (4, 2), (20, 2), (20, 22)])
        path([(7, 21), (7, 5), (17, 7), (17, 23)], True)
        circle(14, 14, .6)
    elif name == 'department':
        rect(3, 7, 18, 14)
        rect(8, 3, 8, 4)
        path([(12, 10), (12, 17)])
        path([(8.5, 13.5), (15.5, 13.5)])
    elif name in ('project', 'configuration', 'checks', 'review', 'report', 'help'):
        rect(5, 3, 15, 19)
        if name == 'project':
            rect(8, 1, 8, 4)
            path([(9, 10), (16, 10)])
            path([(9, 15), (16, 15)])
        elif name == 'checks':
            path([(8, 12), (11, 15), (17, 8)])
        elif name == 'configuration':
            for y, x in ((8, 11), (13, 16), (18, 10)):
                path([(8, y), (17, y)])
                circle(x, y, 1.4)
        elif name == 'review':
            circle(11, 11, 3)
            path([(13, 13), (18, 18)])
        elif name == 'report':
            for x, height in ((9, 4), (13, 9), (17, 6)):
                path([(x, 19), (x, 19-height)])
        else:
            painter.drawText(QRectF(5, 3, 15, 19), Qt.AlignCenter, '?')
    elif name == 'layout':
        rect(3, 4, 18, 16)
        path([(3, 12), (14, 12), (14, 20)])
        path([(10, 4), (10, 12)])
    elif name == 'simulate':
        path([(6, 3), (21, 12), (6, 21)], True)
    elif name in ('fit', 'focus'):
        for pts in ([(3, 9), (3, 3), (9, 3)], [(15, 3), (21, 3), (21, 9)],
                    [(21, 15), (21, 21), (15, 21)], [(9, 21), (3, 21), (3, 15)]):
            path(pts)
        if name == 'fit':
            rect(8, 8, 8, 8)
    elif name in ('properties', 'tree'):
        rect(3, 3, 18, 18)
        x = 15 if name == 'properties' else 9
        path([(x, 3), (x, 21)])
        for y in (7, 11, 15):
            path([(x+2 if name == 'properties' else 5, y), (19 if name == 'properties' else 7, y)])
    elif name == 'more':
        for x in (5, 12, 19):
            circle(x, 12, 1.5)
    else:
        rect(4, 4, 16, 16)
    painter.end()
    return QIcon(pixmap)


def apply_workbench_style(editor):
    """Scope workbench styling to this window; preserve global dialog preferences."""
    c = colours(editor.appearance.value)
    light = editor.appearance.value.theme == 'Light'
    border = '#d5dfeb' if light else c['mid']
    editor.setObjectName('amrWorkbench')
    stylesheet = f'''
        QMainWindow#amrWorkbench {{ background: {c['window']}; }}
        QMainWindow#amrWorkbench QMenuBar {{ background: {c['base']}; padding: 2px 8px; border-bottom: 1px solid {border}; }}
        QMainWindow#amrWorkbench QMenuBar::item {{ padding: 4px 10px; }}
        QMainWindow#amrWorkbench QToolBar {{ background: {c['base']}; border: 0; border-bottom: 1px solid {border}; padding: 4px; spacing: 3px; }}
        QMainWindow#amrWorkbench QToolBar QToolButton {{ border: 1px solid transparent; border-radius: 4px; padding: 5px 8px; color: {c['text']}; background: transparent; }}
        QMainWindow#amrWorkbench QToolBar QToolButton:hover {{ background: {c['alternate']}; border-color: {border}; }}
        QMainWindow#amrWorkbench QToolBar QToolButton:checked {{ background: {c['accent']}; color: {c['selected_text']}; border-color: {c['accent']}; }}
        QMainWindow#amrWorkbench QToolBar QToolButton:disabled {{ color: {c['mid']}; }}
        QMainWindow#amrWorkbench QTreeWidget {{ border: 0; border-radius: 0; background: {c['base']}; padding: 3px; outline: 0; }}
        QMainWindow#amrWorkbench QTreeWidget::item {{ padding: 4px 2px; min-height: 18px; }}
        QMainWindow#amrWorkbench QTreeWidget::item:selected {{ background: {c['accent']}; color: {c['selected_text']}; border-radius: 3px; }}
        QMainWindow#amrWorkbench QSplitter::handle {{ background: {border}; width: 1px; }}
        QMainWindow#amrWorkbench QStatusBar {{ background: {c['base']}; border-top: 1px solid {border}; padding: 2px; }}
        QMainWindow#amrWorkbench QWidget#cadSnapControls QToolButton {{ border: 1px solid {border}; border-radius: 3px; padding: 3px 6px; color: {c['text']}; background: {c['base']}; }}
        QMainWindow#amrWorkbench QWidget#cadSnapControls QToolButton:checked {{ background: {c['accent']}; color: {c['selected_text']}; border-color: {c['accent']}; }}
        QMainWindow#amrWorkbench QWidget#cadSnapControls QToolButton:disabled {{ color: {c['mid']}; }}
        QMainWindow#amrWorkbench QLabel[sectionHeading="true"] {{ font-weight: 600; padding: 5px; }}
        QMainWindow#amrWorkbench QWidget#cadChecksStrip {{ background: {c['base']}; border: 1px solid {border}; border-radius: 4px; }}
        QMainWindow#amrWorkbench QWidget#cadProjectSidebar {{ background: {c['base']}; border-right: 1px solid {border}; }}
    '''
    if editor.styleSheet() != stylesheet:
        editor.setStyleSheet(stylesheet)
    for action in editor.findChildren(QAction):
        name = action.property('cadIcon')
        if name:
            symbol = icon(name, c['text'])
            # Checked tools retain visible symbols over the accent fill.
            symbol.addPixmap(icon(name, c['selected_text']).pixmap(32, 32), QIcon.Normal, QIcon.On)
            action.setIcon(symbol)
    workspace = getattr(editor, 'workspace', None)
    if workspace:
        for name, item in workspace.items.items():
            if name in ('project', 'layout', 'configuration', 'checks', 'simulate', 'review', 'report'):
                symbol = icon(name, c['text'])
                symbol.addPixmap(icon(name, c['selected_text']).pixmap(32, 32), QIcon.Selected)
                item.setIcon(0, symbol)
