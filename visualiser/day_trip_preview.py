"""Modeless daily demand preview with full-content PNG and PDF exports."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile

from PySide6.QtCore import QDate, QEvent, QPointF, QRectF, Qt, QThreadPool, QTimer, Slot
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDateEdit, QDialog, QHBoxLayout, QLabel,
    QFileDialog, QPushButton, QScrollArea, QVBoxLayout, QWidget, QMessageBox)

from amr_day_trip_preview import day_trip_preview, run_dates, write_preview_pdf, stacked_bins, chart_scale
from visualiser.day_schedule import ScheduleJob


class TripPreviewCanvas(QWidget):
    LABEL = 205
    TOP = 300

    def __init__(self,parent=None):
        super().__init__(parent)
        self.preview=None
        self.rows=[]
        self.legend=[]
        self.series=[]
        self.totals=[]
        self.interval=60
        self.zoom=1
        self.setMouseTracking(True)
        self.setAccessibleName('Stacked bar chart of planned trips by time and category')
        self.setFixedWidth(900)
        self.setFixedHeight(380)

    def x(self,minute):
        return 65+(self.width()-83)*minute/1440

    def set_preview(self,preview):
        self.preview=deepcopy(preview)
        self.relayout()

    def set_width(self,width):
        self.setFixedWidth(max(700,width))
        self.relayout()

    def relayout(self):
        self.rows=[]
        self.legend=[]
        self.TOP=300
        if self.preview:
            self.series,self.totals=stacked_bins(self.preview,self.interval)
            x,y=65,260
            line_height=max(20,self.fontMetrics().height()+6)
            for row in self.series:
                label=f"{row['label']} ({row['total']})"
                item_width=min(self.width()-83,self.fontMetrics().horizontalAdvance(label)+34)
                if x+item_width>self.width()-18:x,y=65,y+line_height
                self.legend.append((QRectF(x,y,item_width,line_height),row,label))
                x+=item_width
            self.TOP=max(300,int(y+line_height+12))
            top=self.TOP
            for row in self.preview['categories']:
                notes=([row['notes']] if row['notes'] else [])+row['scope_notes']
                text='\n'.join(notes) or 'No category notes.'
                note_height=self.fontMetrics().boundingRect(
                    QRectF(0,0,self.width()-self.LABEL-24,100000).toRect(),Qt.TextWordWrap,text).height()+18
                height=max(66,note_height)
                self.rows.append((top,height,row,text))
                top+=height
        else:top=self.TOP
        self.setFixedHeight(max(380,int(top+8)))
        self.update()

    def draw_chart(self,painter):
        palette=self.palette()
        painter.fillRect(QRectF(0,0,self.width(),self.TOP),palette.base())
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.preview:
            painter.setPen(palette.text().color())
            painter.drawText(QRectF(0,0,self.width(),self.TOP),Qt.AlignCenter,'Generating the stacked trip chart…')
            return
        step,maximum=chart_scale(self.totals)
        top,bottom=30,215
        left,right=self.x(0),self.x(1440)
        painter.setPen(palette.text().color())
        painter.drawText(QRectF(8,2,90,23),Qt.AlignVCenter,'Trips')
        for value in range(0,maximum+1,step):
            y=bottom-(bottom-top)*value/maximum
            painter.setPen(palette.mid().color())
            painter.drawLine(QPointF(left,y),QPointF(right,y))
            painter.setPen(palette.text().color())
            painter.drawText(QRectF(3,y-10,53,20),Qt.AlignRight|Qt.AlignVCenter,str(value))
        for hour in range(0,25,2):
            x=self.x(hour*60)
            rect=QRectF(x if hour==0 else x-50 if hour==24 else x-25,224,50,22)
            align=Qt.AlignLeft if hour==0 else Qt.AlignRight if hour==24 else Qt.AlignCenter
            painter.drawText(rect,align|Qt.AlignVCenter,f'{hour:02d}:00')
        width=(right-left)/len(self.totals)
        for index,total in enumerate(self.totals):
            if not total:continue
            x=left+(index+.14)*width
            accumulated=0
            for row in self.series:
                value=row['bins'][index]
                if not value:continue
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(row['color']))
                painter.drawRect(QRectF(x,bottom-(bottom-top)*(accumulated+value)/maximum,
                                      width*.72,(bottom-top)*value/maximum))
                accumulated+=value
            if painter.fontMetrics().horizontalAdvance(str(total))<width:
                painter.setPen(palette.text().color())
                painter.drawText(QRectF(left+index*width,bottom-(bottom-top)*total/maximum-22,width,20),
                                 Qt.AlignCenter,str(total))
        for rect,row,label in self.legend:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(row['color']))
            painter.drawRect(QRectF(rect.left(),rect.top()+4,12,12))
            painter.setPen(palette.text().color())
            painter.drawText(rect.adjusted(18,0,-6,0),Qt.AlignVCenter,
                             painter.fontMetrics().elidedText(label,Qt.ElideRight,int(rect.width()-24)))
        painter.setPen(palette.mid().color())
        painter.drawLine(0,self.TOP-1,self.width(),self.TOP-1)

    def draw(self,painter):
        palette=self.palette()
        painter.fillRect(self.rect(),palette.base())
        self.draw_chart(painter)
        for top,height,row,notes in self.rows:
            painter.setPen(palette.text().color())
            painter.drawText(QRectF(8,top+5,self.LABEL-16,24),Qt.AlignVCenter,
                             painter.fontMetrics().elidedText(row['label'],Qt.ElideRight,self.LABEL-16))
            total=f"{row['trips']} planned trips"+(' + more' if row['additional'] else '')
            painter.drawText(QRectF(8,top+30,self.LABEL-16,24),Qt.AlignVCenter,total)
            painter.drawText(QRectF(self.LABEL+8,top+8,self.width()-self.LABEL-24,height-12),Qt.TextWordWrap,notes)
            painter.setPen(palette.mid().color())
            painter.drawLine(0,int(top+height),self.width(),int(top+height))

    def paintEvent(self,event):
        painter=QPainter(self)
        self.draw(painter)

    def chart_tooltip(self,position):
        for rect,row,label in self.legend:
            if rect.contains(position):return label
        if self.preview and self.x(0)<=position.x()<self.x(1440) and 25<=position.y()<=215:
            index=min(len(self.totals)-1,int((position.x()-self.x(0))/(self.x(1440)-self.x(0))*len(self.totals)))
            start=index*self.interval;end=start+self.interval
            lines=[f"{start//60:02d}:{start%60:02d}-{end//60:02d}:{end%60:02d}: {self.totals[index]} planned trips"]
            lines.extend(f"{row['label']}: {row['bins'][index]}" for row in self.series if row['bins'][index])
            return '\n'.join(lines)
        return ''

    def mouseMoveEvent(self,event):
        tip=self.chart_tooltip(event.position())
        if not tip:
            tip=next((notes for top,height,row,notes in self.rows if top<=event.position().y()<top+height),'')
        self.setToolTip(tip)

    def write_png(self, path):
        if not self.preview:
            raise ValueError('Generate a valid preview before exporting.')
        exported=TripPreviewCanvas()
        exported.setFont(self.font())
        # Always export a readable light document, independent of display theme.
        palette=exported.palette()
        from PySide6.QtGui import QPalette
        for role,color in ((QPalette.Base,'white'),(QPalette.Text,'#18242d'),(QPalette.Mid,'#ccd3d9'),
                           (QPalette.AlternateBase,'#edf2f6'),(QPalette.Highlight,'#2574a9')):
            palette.setColor(role,QColor(color))
        exported.setPalette(palette)
        exported.interval=self.interval
        exported.set_width(1400)
        exported.set_preview(self.preview)
        header=112
        height=exported.height()+header+58
        if height*2>30000:
            raise ValueError('This preview is too tall for one PNG. Save it as a PDF instead.')
        image=QImage(exported.width()*2,height*2,QImage.Format_RGB32)
        if image.isNull():
            raise ValueError('There is not enough memory to export this PNG. Save as PDF instead.')
        image.fill(QColor('white'))
        image.setText('Description',self.preview['explanation'])
        painter=QPainter(image)
        try:
            painter.scale(2,2)
            painter.setPen(QColor('#18242d'))
            font=self.font()
            font.setPointSize(max(14,font.pointSize()+4))
            painter.setFont(font)
            painter.drawText(QRectF(12,10,1376,34),Qt.AlignVCenter,f"Demand preview - {self.preview['date']}")
            font.setPointSize(max(9,font.pointSize()-4))
            painter.setFont(font)
            painter.drawText(QRectF(12,46,1376,30),Qt.AlignVCenter,
                f"{self.preview['source']} | {self.preview['trips']} planned trips | {self.preview['quantity']:g} load units | {self.interval}-minute stacked bars")
            painter.translate(0,header)
            painter.setFont(exported.font())
            exported.draw(painter)
            painter.translate(0,-header)
            painter.setPen(QColor('#18242d'))
            painter.setFont(exported.font())
            painter.drawText(QRectF(12,height-48,1376,42),Qt.TextWordWrap,self.preview['explanation'])
        finally:
            painter.end()
        if not image.save(str(path),'PNG'):
            raise ValueError('The PNG could not be written. Choose a writable folder.')


class StackedChartHeader(QWidget):
    """Keep the complete chart in view while category notes scroll beneath it."""
    def __init__(self,scroll,canvas):
        super().__init__(scroll.viewport())
        self.canvas=canvas
        self.setMouseTracking(True)
        self.setAccessibleName('Fixed stacked trip chart and category legend')
        self.raise_()

    def paintEvent(self,event):
        painter=QPainter(self)
        self.canvas.draw_chart(painter)

    def mouseMoveEvent(self,event):
        self.setToolTip(self.canvas.chart_tooltip(event.position()))


class DayTripPreviewDialog(QDialog):
    """A live, modeless companion to the editable schedule."""
    def __init__(self, configuration, source, weekday=0, adjust=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Daily demand preview')
        self.setModal(False)
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint,True)
        self.resize(1100,750)
        self.configuration=configuration
        self.source=source
        self.adjust=adjust
        self.preview=None
        self.job=None
        self.pending=False
        self.valid_signature=None
        layout=QVBoxLayout(self)
        toolbar=QHBoxLayout()
        toolbar.addWidget(QLabel('Preview date'))
        self.date=QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat('ddd dd MMM yyyy')
        self.date.setAccessibleName('Demand preview date')
        config=configuration()
        start,end,last=run_dates(config)
        chosen=min(start.date()+timedelta(days=(weekday-start.weekday())%7),last)
        self.date.setDateRange(QDate(start.year,start.month,start.day),QDate(last.year,last.month,last.day))
        self.date.setDate(QDate(chosen.year,chosen.month,chosen.day))
        toolbar.addWidget(self.date)
        self.interval=QComboBox()
        for label,value in (('Hourly',60),('30 minutes',30),('15 minutes',15)):
            self.interval.addItem(label,value)
        self.interval.setAccessibleName('Stacked chart time interval')
        toolbar.addWidget(self.interval)
        self.refresh_button=QPushButton('Refresh preview')
        self.pdf=QPushButton('Save PDF…')
        self.png=QPushButton('Save PNG…')
        for button in (self.refresh_button,self.pdf,self.png):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.totals=QLabel('Generating the daily trip preview…')
        self.totals.setWordWrap(True)
        layout.addWidget(self.totals)
        self.scroll=QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.canvas=TripPreviewCanvas()
        self.scroll.setWidget(self.canvas)
        self.ruler=StackedChartHeader(self.scroll,self.canvas)
        self.scroll.viewport().installEventFilter(self)
        layout.addWidget(self.scroll,1)
        self.explanation=QLabel('Stacked bars show planned trips split by category. The chart stays visible while notes scroll.')
        self.explanation.setWordWrap(True)
        layout.addWidget(self.explanation)
        controls=QHBoxLayout()
        self.categories=QComboBox()
        self.categories.setAccessibleName('Category to adjust in the day schedule')
        controls.addWidget(self.categories,1)
        self.adjust_button=QPushButton('Adjust category in schedule')
        controls.addWidget(self.adjust_button)
        self.close_button=QPushButton('Close')
        controls.addWidget(self.close_button)
        layout.addLayout(controls)
        self.status=QLabel('')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.timer=QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.refresh_preview)
        self.date.dateChanged.connect(self.source_changed)
        self.interval.currentIndexChanged.connect(self.interval_changed)
        self.refresh_button.clicked.connect(self.refresh_preview)
        self.pdf.clicked.connect(lambda:self.export_file('pdf'))
        self.png.clicked.connect(lambda:self.export_file('png'))
        self.close_button.clicked.connect(self.close)
        self.adjust_button.clicked.connect(self.adjust_category)
        self.update_buttons()

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type()==QEvent.Resize:
            self.canvas.set_width(self.scroll.viewport().width())
            self.ruler.setGeometry(0,0,self.scroll.viewport().width(),self.canvas.TOP)
            self.ruler.raise_()
        return super().eventFilter(watched,event)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.fit_explanations()

    def fit_explanations(self):
        width=max(200,self.width()-24)
        for name in ('totals','explanation','status'):
            label=getattr(self,name,None)
            if label is not None:
                label.setMinimumHeight(max(label.fontMetrics().height(),label.heightForWidth(width)))

    def interval_changed(self,*_):
        self.canvas.interval=self.interval.currentData()
        self.canvas.relayout()
        self.ruler.setGeometry(0,0,self.scroll.viewport().width(),self.canvas.TOP)
        self.ruler.update()

    def signature(self):
        return json.dumps([self.configuration(),self.date.date().toString('yyyy-MM-dd'),self.source()],sort_keys=True,default=str)

    def source_changed(self,*_):
        self.valid_signature=None
        self.totals.setText('Schedule changed - updating the planned trip counts…')
        self.status.setText('Schedule changed. Refreshing the trip preview…')
        self.update_buttons()
        if self.job:
            self.pending=True
        elif self.isVisible():
            self.timer.start()

    def hideEvent(self,event):
        self.timer.stop()
        super().hideEvent(event)

    def refresh_preview(self):
        self.timer.stop()
        if self.job:
            self.pending=True
            return
        try:
            config=deepcopy(self.configuration())
            source=self.source()
            selected=self.date.date().toString('yyyy-MM-dd')
            signature=self.signature()
        except Exception as exc:
            self.status.setText('Preview unavailable: '+str(exc))
            self.totals.setText('Preview unavailable. The previous chart is not current.')
            self.valid_signature=None
            self.update_buttons()
            return
        self.job_signature=signature
        self.valid_signature=None
        self.status.setText('Calculating planned trips from the demand generator…')
        self.totals.setText(f'Calculating planned trips for {selected}…')
        self.job=ScheduleJob(lambda:day_trip_preview(config,selected,source=source))
        self.job.signals.finished.connect(self.finish_preview_job,Qt.QueuedConnection)
        QThreadPool.globalInstance().start(self.job)
        self.update_buttons()

    @Slot(object,str)
    def finish_preview_job(self,result,error):
        self.job=None
        self.valid_signature=None
        try:
            stale=self.job_signature!=self.signature()
            if stale:
                self.pending=True
                self.status.setText('The schedule changed during calculation. Updating the preview…')
            elif error:
                self.status.setText('Preview unavailable: '+error)
                self.totals.setText('Preview unavailable. The previous chart is not current.')
            else:
                self.preview=result
                self.valid_signature=self.job_signature
                self.canvas.set_preview(result)
                self.ruler.setGeometry(0,0,self.scroll.viewport().width(),self.canvas.TOP)
                self.ruler.raise_()
                self.ruler.update()
                self.totals.setText(f"{result['date']} · {result['source']} · {result['trips']} planned trips · {result['quantity']:g} load units"
                                    + (' · Additional trips depend on returns or on-demand work' if result['additional'] else ''))
                self.explanation.setText(result['explanation'])
                selected=self.categories.currentData()
                self.categories.clear()
                for row in result['categories']:
                    self.categories.addItem(f"{row['label']} - {row['trips']} planned trips",row['key'])
                index=self.categories.findData(selected)
                if index>=0:self.categories.setCurrentIndex(index)
                self.status.setText('Preview is current. Exports include every category, including rows outside the visible area.')
        except Exception as exc:
            self.valid_signature=None
            self.status.setText('Preview unavailable: '+str(exc))
        self.update_buttons()
        self.fit_explanations()
        if self.pending and self.isVisible():
            self.pending=False
            self.timer.start(0)

    def update_buttons(self):
        ready=bool(self.preview and self.valid_signature and not self.job)
        self.pdf.setEnabled(ready)
        self.png.setEnabled(ready)
        self.refresh_button.setEnabled(not self.job)
        self.adjust_button.setEnabled(bool(self.adjust and self.preview))

    def adjust_category(self):
        if self.adjust and self.categories.currentData():
            self.adjust(self.categories.currentData())

    def export_to(self,path,kind):
        if self.job or not self.valid_signature or self.signature()!=self.valid_signature:
            self.source_changed()
            raise ValueError('Refresh the preview before exporting changed demand.')
        # Render before replacing a target so a failed export preserves the prior file.
        with tempfile.TemporaryDirectory() as folder:
            temporary=Path(folder)/('demand-preview.'+kind)
            if kind=='pdf':write_preview_pdf(temporary,self.preview,self.interval.currentData())
            elif kind=='png':self.canvas.write_png(temporary)
            else:raise ValueError('Choose PDF or PNG.')
            Path(path).write_bytes(temporary.read_bytes())

    def export_file(self,kind):
        suggested=f"demand-preview-{self.date.date().toString('yyyy-MM-dd')}.{kind}"
        target,_=QFileDialog.getSaveFileName(self,'Save demand preview',suggested,
                                          'PDF documents (*.pdf)' if kind=='pdf' else 'PNG images (*.png)')
        if not target:return
        path=Path(target)
        if path.suffix.lower()!='.'+kind:
            path=path.with_suffix('.'+kind)
            if path.exists() and QMessageBox.question(self,'Replace existing file?',f'Replace {path}?',
                QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:
            self.export_to(path,kind)
            self.status.setText(f'Saved {path.name}.')
        except Exception as exc:
            QMessageBox.warning(self,'Preview export failed',str(exc))
