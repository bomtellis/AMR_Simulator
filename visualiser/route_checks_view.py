"""Read-only navigation results shared by Check and frozen-run Review."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QSizePolicy


class RouteChecksView(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.rows=[];self.context='';self.execution='not_run'
        layout=QVBoxLayout(self)
        self.summary=QLabel();self.summary.setWordWrap(True)
        self.summary.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);layout.addWidget(self.summary)
        self.search=QLineEdit();self.search.setPlaceholderText('Find a task, demand rule, profile, location or blocked route…')
        self.search.textChanged.connect(self.filter);layout.addWidget(self.search)
        self.table=QTableWidget(0,8)
        self.table.setHorizontalHeaderLabels(['Source / scope','Profile','Leg','From','To','Result','Department','Task / rule'])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7,QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self.explain);layout.addWidget(self.table,1)
        self.details=QLabel('Select a route to inspect its permissions check.');self.details.setWordWrap(True)
        self.details.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);layout.addWidget(self.details)
        self.set_report(None,'Checks have not run.')

    def set_report(self,report,context):
        self.rows=(report or {}).get('route_checks',[])
        self.execution=(report or {}).get('check_groups',{}).get('task_routes',{}).get('execution','not_run')
        self.table.setRowCount(len(self.rows))
        for index,row in enumerate(self.rows):
            values=[row['source'],row['profile'] or 'Unrestricted',row['leg'],row['pickup'],row['dropoff'],row['status'],row['department'],row['name']]
            for col,text in enumerate(values):
                item=QTableWidgetItem(text);item.setToolTip(row['reason']+'\n'+row['path']);self.table.setItem(index,col,item)
        self.set_context(context);self.filter();self.explain()

    def set_context(self,context):
        self.context=context
        passed=sum(row['status']=='Reachable' for row in self.rows)
        self.summary.setText(f'{context}\nTask route checks: {passed} reachable · {len(self.rows)-passed} blocked or invalid · '
                             f"coverage {self.execution.replace('_',' ')}. Counts are route definitions, not releases.")
        self.summary.setToolTip('Includes active demand rules and configured returns; runtime releases remain conditional. '
                               'Checks directed graph permissions including lifts and task extensions; clearance, capacity, outages and timing need simulation.')

    def filter(self,*_):
        query=self.search.text().casefold()
        for index,row in enumerate(self.rows):self.table.setRowHidden(index,query not in ' '.join(str(v) for v in row.values()).casefold())

    def explain(self):
        index=self.table.currentRow()
        self.details.setText(self.rows[index]['reason']+'\nSetting: '+self.rows[index]['path'] if 0<=index<len(self.rows) else 'Select a route to inspect its permissions check.')
