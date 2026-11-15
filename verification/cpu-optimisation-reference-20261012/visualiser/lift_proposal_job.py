"""Generate proposals off the UI thread from a private input snapshot."""
from threading import Event
from PySide6.QtCore import QObject,QRunnable,Signal
from amr_lift_planning_geometry import generate_sites,build_proposals


class ProposalCancelled(Exception):
    pass


class ProposalSignals(QObject):
    progress=Signal(str,int)
    finished=Signal(object,str,bool)


class ProposalJob(QRunnable):
    def __init__(self,config,geometry,options,requests):
        super().__init__()
        self.config=config;self.geometry=geometry;self.options=options;self.requests=requests
        self.signals=ProposalSignals();self.cancelled=Event()

    def progress(self,message,value):
        if self.cancelled.is_set():raise ProposalCancelled()
        self.signals.progress.emit(message,value)

    def run(self):
        try:
            self.progress('Screening aligned shaft and landing sites on every floor…',0)
            sites=generate_sites(self.config,self.geometry,self.options,self.requests,
                progress=lambda n,total:self.progress('Screening aligned shaft and landing sites on every floor…',int(70*n/max(total,1))))
            self.progress(f'{len(sites)} aligned sites found. Checking route-permitted layout connectors…',70)
            proposals,overlays=build_proposals(self.config,self.geometry,sites,self.options,
                progress=lambda n,total:self.progress(f'Checking candidate layout {n+1}/{total}: route permissions and floor connectors…',70+int(29*n/max(total,1))))
            self.progress('Layout proposals generated.',100)
            self.signals.finished.emit((sites,proposals,overlays),'',False)
        except ProposalCancelled:
            self.signals.finished.emit(None,'Proposal generation cancelled. Previous proposals and evidence are retained.',True)
        except Exception as exc:
            self.signals.finished.emit(None,str(exc),False)
