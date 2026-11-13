from PySide6.QtWidgets import *
from core.database import Database
from core.scope import normalize_origin
from core.scan_service import PassiveScanService
from ui.workers import OperationNotifier
from reporting.exporters import export_json, export_pdf

TEXT = {
 "en":{"projects":"Projects","new":"New project","scan":"Run passive HTTPS checks",
 "finding":"Add manual finding","asset":"Add authorized asset","json":"Export JSON",
 "pdf":"Export PDF","select":"Select or create a project","title":"AEGISSEC ENTERPRISE",
 "lang":"فارسی","auth":"Authorization reference","target":"Exact authorized origin",
 "name":"Project name","done":"Completed","no_project":"Select a project first"},
 "fa":{"projects":"پروژه‌ها","new":"پروژه جدید","scan":"بررسی غیرفعال HTTPS",
 "finding":"ثبت یافته دستی","asset":"افزودن دارایی مجاز","json":"خروجی JSON",
 "pdf":"خروجی PDF","select":"یک پروژه انتخاب یا ایجاد کنید","title":"ایجیس‌سک سازمانی",
 "lang":"English","auth":"مرجع مجوز کتبی","target":"مبدأ دقیق مجاز",
 "name":"نام پروژه","done":"انجام شد","no_project":"ابتدا یک پروژه انتخاب کنید"}
}
class MainWindow(QMainWindow):
 def __init__(self):
  super().__init__(); self.db=Database(); self.scan_service=PassiveScanService(self.db); self.notifier=OperationNotifier(); self.notifier.finished.connect(self.scan_finished); self.scan_op=None; self.project=None; self.language="en"
  self.resize(1250,790); self.setWindowTitle("AegisSec Enterprise v0.3")
  self.setStyleSheet("""
   QMainWindow{background:#101722;color:#e8eef7} QWidget{color:#e8eef7;font-size:13px}
   QLineEdit,QTextEdit,QComboBox,QListWidget,QTableWidget{background:#182333;border:1px solid #34465f;border-radius:6px;padding:6px}
   QPushButton{background:#176b87;border:0;border-radius:6px;padding:9px 13px}
   QPushButton:hover{background:#2186a6} QHeaderView::section{background:#23364b;padding:6px}
  """)
  self.build(); self.load_projects(); self.translate()
 def build(self):
  c=QWidget(); self.setCentralWidget(c); root=QVBoxLayout(c)
  top=QHBoxLayout(); self.heading=QLabel(); self.heading.setStyleSheet("font-size:23px;font-weight:700;color:#65c7df")
  top.addWidget(self.heading); top.addStretch(); self.lang=QPushButton(); self.lang.clicked.connect(self.toggle_language); top.addWidget(self.lang)
  root.addLayout(top)
  split=QSplitter(); root.addWidget(split,1)
  left=QWidget(); ll=QVBoxLayout(left); self.project_label=QLabel(); ll.addWidget(self.project_label)
  self.projects_list=QListWidget(); self.projects_list.currentRowChanged.connect(self.select_project); ll.addWidget(self.projects_list)
  self.new_btn=QPushButton(); self.new_btn.clicked.connect(self.new_project); ll.addWidget(self.new_btn)
  split.addWidget(left)
  right=QWidget(); rl=QVBoxLayout(right); self.project_title=QLabel(); rl.addWidget(self.project_title)
  row=QHBoxLayout()
  self.scan_btn=QPushButton(); self.scan_btn.clicked.connect(self.scan)
  self.find_btn=QPushButton(); self.find_btn.clicked.connect(self.add_finding)
  self.asset_btn=QPushButton(); self.asset_btn.clicked.connect(self.add_asset)
  self.json_btn=QPushButton(); self.json_btn.clicked.connect(self.export_j)
  self.pdf_btn=QPushButton(); self.pdf_btn.clicked.connect(self.export_p)
  for b in (self.scan_btn,self.find_btn,self.asset_btn,self.json_btn,self.pdf_btn): row.addWidget(b)
  rl.addLayout(row)
  self.tabs=QTabWidget(); rl.addWidget(self.tabs,1)
  self.findings_table=QTableWidget(0,6); self.findings_table.setHorizontalHeaderLabels(["ID","Title","Severity","Confidence","Status","URL"]); self.findings_table.horizontalHeader().setStretchLastSection(True)
  self.assets_table=QTableWidget(0,3); self.assets_table.setHorizontalHeaderLabels(["ID","Origin","Type"]); self.assets_table.horizontalHeader().setStretchLastSection(True)
  self.tabs.addTab(self.findings_table,"Findings / یافته‌ها"); self.tabs.addTab(self.assets_table,"Assets / دارایی‌ها")
  self.notice=QLabel("Authorized scope only. Passive check makes one GET request and does not follow redirects.")
  self.notice.setWordWrap(True); self.notice.setStyleSheet("color:#9eb0c7"); rl.addWidget(self.notice)
  split.addWidget(right); split.setSizes([260,980])
  for b in (self.scan_btn,self.find_btn,self.asset_btn,self.json_btn,self.pdf_btn): b.setEnabled(False)
 def translate(self):
  t=TEXT[self.language]; self.heading.setText(t["title"]); self.lang.setText(t["lang"])
  self.project_label.setText(t["projects"]); self.new_btn.setText(t["new"])
  self.scan_btn.setText(t["scan"]); self.find_btn.setText(t["finding"]); self.asset_btn.setText(t["asset"])
  self.json_btn.setText(t["json"]); self.pdf_btn.setText(t["pdf"])
  if not self.project: self.project_title.setText(t["select"])
 def toggle_language(self):
  self.language="fa" if self.language=="en" else "en"; self.translate()
 def load_projects(self):
  self.projects_list.clear()
  for p in self.db.projects(): self.projects_list.addItem(f"{p['name']} — {p['target']}")
  if self.projects_list.count(): self.projects_list.setCurrentRow(0)
 def new_project(self):
  t=TEXT[self.language]
  name,ok=QInputDialog.getText(self,t["new"],t["name"])
  if not ok or not name.strip(): return
  target,ok=QInputDialog.getText(self,t["new"],t["target"])
  if not ok: return
  try: target=normalize_origin(target)
  except Exception as e: QMessageBox.warning(self,"Invalid origin",str(e)); return
  auth,ok=QInputDialog.getText(self,t["new"],t["auth"])
  if not ok or not auth.strip(): QMessageBox.warning(self,"Authorization required","A written authorization reference is required."); return
  self.db.create_project(name.strip(),target,auth.strip()); self.load_projects()
 def select_project(self,row):
  ps=self.db.projects()
  self.project=ps[row] if 0<=row<len(ps) else None
  enabled=self.project is not None
  for b in (self.scan_btn,self.find_btn,self.asset_btn,self.json_btn,self.pdf_btn): b.setEnabled(enabled)
  if enabled:
   self.project_title.setText(f"{self.project['name']} | {self.project['target']}")
   self.refresh()
  else: self.project_title.setText(TEXT[self.language]["select"])
 def refresh(self):
  fs=self.db.findings(self.project["id"]); self.findings_table.setRowCount(len(fs))
  for r,f in enumerate(fs):
   for c,v in enumerate([f["id"],f["title"],f["severity"],f["confidence"],f["status"],f["url"]]): self.findings_table.setItem(r,c,QTableWidgetItem(str(v)))
  assets=self.db.assets(self.project["id"]); self.assets_table.setRowCount(len(assets))
  for r,a in enumerate(assets):
   for c,v in enumerate([a["id"],a["origin"],a["asset_type"]]): self.assets_table.setItem(r,c,QTableWidgetItem(str(v)))
 def scan(self):
  if self.scan_op is not None:  # button acts as Cancel while a scan runs
   self.scan_op.cancel(); return
  p=self.project
  try:
   self.scan_op=self.scan_service.start(p,on_done=self.notifier.callback)
   self.scan_btn.setText("Cancel scan")
   self.scan_project=p
  except PermissionError as e: QMessageBox.warning(self,"Stopped",str(e))
  except Exception as e: self.db.log(p["id"],"PASSIVE_CHECK_STOPPED",str(e)); QMessageBox.warning(self,"Stopped",str(e))
 def scan_finished(self,op):
  p=self.scan_project; self.scan_op=None; self.translate()
  try:
   n=self.scan_service.finalize(p,op)
   if self.project and self.project["id"]==p["id"]: self.refresh()
   st=op.status
   if st.state.value=="SUCCEEDED": QMessageBox.information(self,"Completed",f"{n} observations recorded for analyst review ({st.duration_ms} ms).")
   else: QMessageBox.warning(self,st.state.value.title(),st.error or st.state.value)
  except Exception as e: QMessageBox.warning(self,"Error",str(e))
 def add_asset(self):
  origin,ok=QInputDialog.getText(self,"Authorized asset","Exact origin (must be covered by written authorization):")
  if not ok: return
  try: origin=normalize_origin(origin)
  except Exception as e: QMessageBox.warning(self,"Invalid origin",str(e)); return
  kind,ok=QInputDialog.getItem(self,"Asset type","Type:",["Web origin","API origin","Other authorized endpoint"],0,False)
  if not ok: return
  self.db.add_asset(self.project["id"],origin,kind); self.refresh()
 def add_finding(self):
  title,ok=QInputDialog.getText(self,"Manual finding","Finding title:")
  if not ok or not title.strip(): return
  severity,ok=QInputDialog.getItem(self,"Severity","Severity:",["Info","Low","Medium","High","Critical"],1,False)
  if not ok: return
  confidence,ok=QInputDialog.getItem(self,"Confidence","Confidence:",["Low","Medium","High"],1,False)
  if not ok: return
  url,_=QInputDialog.getText(self,"Affected URL","Affected URL (optional):")
  evidence,_=QInputDialog.getMultiLineText(self,"Evidence","Evidence and safe reproduction notes:")
  remediation,_=QInputDialog.getMultiLineText(self,"Remediation","Recommended remediation:")
  ref,_=QInputDialog.getText(self,"Reference","CWE / OWASP / advisory reference (optional):")
  self.db.add_finding(self.project["id"],title,severity,confidence,url,"Needs review",evidence,remediation,ref); self.refresh()
 def export_j(self):
  p=self.project; path,_=QFileDialog.getSaveFileName(self,"Export JSON",f"{p['name']}.json","JSON (*.json)")
  if path: export_json(path,p,self.db.findings(p["id"]),self.db.assets(p["id"])); self.db.log(p["id"],"JSON_EXPORTED",path)
 def export_p(self):
  p=self.project; path,_=QFileDialog.getSaveFileName(self,"Export PDF",f"{p['name']}.pdf","PDF (*.pdf)")
  if path:
   try: export_pdf(path,p,self.db.findings(p["id"]),self.language,assets=self.db.assets(p["id"])); self.db.log(p["id"],"PDF_EXPORTED",path); QMessageBox.information(self,"Export","PDF report created.")
   except Exception as e: QMessageBox.warning(self,"PDF error",str(e))
