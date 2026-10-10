"""Profile access and blocked directions available directly beside the Layout."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QToolBar,QLabel,QPushButton,QCheckBox,QColorDialog


class RouteViewToolbar(QToolBar):
    def __init__(self,editor):
        super().__init__('Route profile views',editor)
        self.editor=editor;self.expanded=False;self.setObjectName('layoutRouteViews');self.setMovable(False);self.setFloatable(False)
        self.addWidget(QLabel('Route view '));self.profile=editor.route_display_combo
        self.profile.setMinimumContentsLength(14);self.addWidget(self.profile)
        self.permitted=QPushButton('Profile colour…');self.permitted.clicked.connect(self.choose_profile_colour)
        self.addWidget(self.permitted)
        self.blocked=QCheckBox('Show blocked directions');self.blocked.setChecked(True)
        self.blocked.setToolTip('Dotted edges and arrows identify graph directions excluded by the selected profile.')
        self.blocked.toggled.connect(editor.refresh_canvas);self.addWidget(self.blocked)
        self.blocked_colour=QPushButton('Blocked colour…');self.blocked_colour.clicked.connect(self.choose_blocked_colour)
        self.addWidget(self.blocked_colour);self.addWidget(editor.route_labels_check)
        self.details=QPushButton('Profile details…');self.details.clicked.connect(editor.show_route_identification)
        self.addWidget(self.details)
        self.profile.currentIndexChanged.connect(lambda: self.set_expanded(True));editor.route_styles.changed.connect(self.sync)
        editor.workspace.central_layout.insertWidget(1,self);self.sync()

    def sync(self,*_):
        selected=self.profile.currentData();single=isinstance(selected,str)
        self.permitted.setEnabled(single);self.blocked.setEnabled(single);self.blocked_colour.setEnabled(single)
        self.permitted.setToolTip(f'{selected}: '+self.editor.route_styles.get(selected)['colour'] if single else 'Select one profile to change its colour.')
        self.blocked_colour.setToolTip('Blocked graph directions: '+self.editor.route_styles.blocked_colour)
        self.setVisible(self.editor.workspace.stage=='layout' and self.expanded)
        self.editor.cad_toolbar.route_views_action.setChecked(self.expanded)

    def set_expanded(self,expanded):
        self.expanded=expanded;self.sync()

    def choose_profile_colour(self):
        name=self.profile.currentData()
        if not isinstance(name,str):return
        style=self.editor.route_styles.get(name)
        colour=QColorDialog.getColor(QColor(style['colour']),self,'Permitted profile edge colour')
        if colour.isValid():
            try:
                self.editor.route_styles.save(name,dict(style,colour=colour.name()))
            except (ValueError,OSError) as exc:self.editor.set_status(str(exc))

    def choose_blocked_colour(self):
        colour=QColorDialog.getColor(QColor(self.editor.route_styles.blocked_colour),self,'Blocked edge colour')
        if colour.isValid():
            try:self.editor.route_styles.save_blocked_colour(colour.name())
            except (ValueError,OSError) as exc:self.editor.set_status(str(exc))
