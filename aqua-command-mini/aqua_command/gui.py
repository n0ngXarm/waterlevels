"""Native desktop UI. File reads happen only on explicit operator actions."""
import queue
import threading
import tkinter as tk
from collections import Counter
from datetime import datetime, timezone
from tkinter import filedialog, messagebox, ttk

from .config import ConfigError
from .exporter import ExportError
from .importer import InputError
from .ledger import Ledger, LedgerError
from .session import Session, demo_csv
from .telegram_test import TEST_MESSAGE, get_machine_id, readiness, run_test

REASONS_TH = {
    'TAG_NOT_ALLOWED': 'Tag ไม่อยู่ในรายการอนุญาต',
    'VALUE_NOT_MAPPED': 'ค่าไม่ตรง mapping 0/1',
    'QUALITY_NOT_ACCEPTED': 'Quality ไม่ผ่าน',
    'TIMESTAMP_MISSING': 'ไม่มีเวลา',
    'TIMESTAMP_INVALID_ISO8601_REQUIRED': 'รูปแบบเวลาไม่รองรับ',
    'TIMESTAMP_OFFSET_INVALID': 'Timezone ไม่รองรับ',
    'TIMEZONE_REQUIRED': 'ต้องระบุ timezone',
    'STALE': 'ข้อมูลเก่าเกินกำหนด',
    'FUTURE_TIMESTAMP': 'เวลาอยู่ในอนาคตเกินกำหนด',
    'UNORDERED_SAMPLE': 'Tag นี้มี sample ที่เรียงเวลาไม่ได้',
    'CONFLICTING_SAMPLES': 'เวลาเดียวกันแต่ค่าหรือ quality ขัดกัน',
    'COLUMN_COUNT': 'จำนวน column ไม่ตรงหัวตาราง',
    'HISTORY_CONFLICT': 'ขัดกับประวัติเดิมที่เวลาเดียวกัน',
}
DECISIONS_TH = {'CANDIDATE': 'เข้าเกณฑ์ dry-run', 'BLOCKED': 'ระงับ', 'SUPERSEDED': 'มี sample ใหม่กว่า',
                'DUPLICATE_IN_FILE': 'ซ้ำในไฟล์', 'DUPLICATE_HISTORY': 'ซ้ำกับประวัติ',
                'OUT_OF_ORDER': 'เก่ากว่าประวัติ', 'UNCHANGED': 'สถานะเดิม'}
HANDLED = (ConfigError, ExportError, InputError, LedgerError, OSError, ValueError)


class App:
    def __init__(self, root, session):
        self.root, self.session = root, session
        self.rows_shown = []
        self.test_running = False
        self.results = queue.Queue()
        root.title('AQUA COMMAND Mini v0.1 | PoC • DRY-RUN')
        root.geometry('1240x760')
        root.minsize(940, 620)
        root.configure(background='#edf3f5')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 11))
        style.configure('TFrame', background='#edf3f5')
        style.configure('TLabel', background='#edf3f5', foreground='#17303b')
        style.configure('TButton', padding=(12, 8))
        style.configure('Treeview', rowheight=34, background='white', fieldbackground='white', font=('Segoe UI', 10))
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'), padding=(8, 8))
        style.configure('TNotebook.Tab', padding=(18, 10))

        banner = tk.Frame(root, background='#103b4b', padx=22, pady=16)
        banner.pack(fill='x')
        tk.Label(banner, text='AQUA COMMAND  /  MINI', background='#103b4b', foreground='white',
                 font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        tk.Label(banner, text='v0.1  •  PoC  •  DRY-RUN  |  อ่านไฟล์ในเครื่อง  |  ไม่ใช่สถานะ Live',
                 background='#103b4b', foreground='#a9e5e2', font=('Segoe UI', 11)).pack(anchor='w', pady=(4, 0))
        body = ttk.Frame(root, padding=18)
        body.pack(fill='both', expand=True)
        body.rowconfigure(2, weight=1)
        body.columnconfigure(0, weight=1)
        controls = ttk.Frame(body)
        controls.grid(row=0, column=0, sticky='ew')
        ttk.Button(controls, text='1  ข้อมูลจำลองใหม่', command=self.load_demo).pack(side='left', padx=(0, 8))
        ttk.Button(controls, text='2  เลือก TXT / CSV', command=self.choose_file).pack(side='left', padx=(0, 8))
        ttk.Button(controls, text='เลือกโปรไฟล์ JSON', command=self.choose_profile).pack(side='left', padx=(0, 8))
        self.profile_label = ttk.Label(controls, text='Profile: ' + session.profile.profile_id)
        self.profile_label.pack(side='right')
        self.file_info = tk.StringVar(value='เริ่มด้วยข้อมูลจำลอง หรือเลือกเฉพาะไฟล์ที่เจ้าหน้าที่ได้รับอนุญาตส่งออกมา')
        ttk.Label(body, textvariable=self.file_info, wraplength=1150).grid(row=1, column=0, sticky='ew', pady=(12, 8))
        notebook = ttk.Notebook(body)
        notebook.grid(row=2, column=0, sticky='nsew')
        file_tab, test_tab = ttk.Frame(notebook, padding=12), ttk.Frame(notebook, padding=16)
        notebook.add(file_tab, text='พรีวิวและส่งออกในเครื่อง')
        notebook.add(test_tab, text='Telegram TEST จำลอง')
        file_tab.rowconfigure(1, weight=1)
        file_tab.columnconfigure(0, weight=1)
        self.summary = tk.StringVar(value='ยังไม่มีไฟล์ — ค่าเริ่มต้นอนุญาตเฉพาะ DEMO_PUMP_01 และ DEMO_VALVE_01')
        ttk.Label(file_tab, textvariable=self.summary, font=('Segoe UI', 12, 'bold'), wraplength=1120).grid(row=0, column=0, sticky='ew', pady=(0, 10))
        table_frame = ttk.Frame(file_tab)
        table_frame.grid(row=1, column=0, sticky='nsew')
        columns = ('row', 'tag', 'timestamp', 'value', 'quality', 'state', 'decision', 'reason')
        self.table = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode='browse')
        headings = ('แถว', 'Tag', 'Timestamp ต้นฉบับ', 'Value', 'Quality', 'State', 'ผล dry-run', 'เหตุผล')
        widths = (55, 170, 220, 65, 75, 85, 145, 285)
        for column, heading, width in zip(columns, headings, widths):
            self.table.heading(column, text=heading)
            self.table.column(column, width=width, minwidth=45, stretch=column in ('tag', 'reason'))
        scroll_y = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        scroll_x = ttk.Scrollbar(table_frame, orient='horizontal', command=self.table.xview)
        self.table.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.table.grid(row=0, column=0, sticky='nsew')
        scroll_y.grid(row=0, column=1, sticky='ns')
        scroll_x.grid(row=1, column=0, sticky='ew')
        self.table.tag_configure('ON', foreground='#056651')
        self.table.tag_configure('OFF', foreground='#1d4f91')
        self.table.tag_configure('UNKNOWN', foreground='#855900')
        self.table.tag_configure('ERROR', foreground='#a52626')
        self.table.bind('<Double-1>', self.show_details)
        actions = ttk.Frame(file_tab)
        actions.grid(row=2, column=0, sticky='ew', pady=(12, 4))
        ttk.Button(actions, text='ตรวจเกณฑ์อีกครั้ง', command=self.refresh).pack(side='left', padx=(0, 8))
        self.export_button = ttk.Button(actions, text='3  Export structured CSV', command=self.export_file, state='disabled')
        self.export_button.pack(side='left', padx=(0, 8))
        self.commit_button = ttk.Button(actions, text='บันทึกประวัติ dry-run', command=self.commit_dry_run, state='disabled')
        self.commit_button.pack(side='left')
        ttk.Label(file_tab, text='พรีวิวไม่บันทึกประวัติ • ตรวจ freshness ใหม่เมื่อกดปุ่ม • ดับเบิลคลิกแถวเพื่อดูรายละเอียด',
                  wraplength=1100).grid(row=3, column=0, sticky='ew', pady=(6, 0))

        test_tab.rowconfigure(2, weight=1)
        test_tab.columnconfigure(0, weight=1)
        ttk.Label(test_tab, text='ส่งเฉพาะ TEST จำลองที่แสดงด้านล่าง', font=('Segoe UI', 15, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w')
        ttk.Label(test_tab, text='ข้อมูลจากไฟล์, Tag ของสถานี และ hash ไฟล์ ไม่อยู่ในข้อความที่จะส่ง',
                  wraplength=850).grid(row=1, column=0, columnspan=2, sticky='ew', pady=(4, 12))
        preview = tk.Text(test_tab, height=7, wrap='word', background='white', relief='flat', padx=14, pady=12,
                          font=('Consolas', 11))
        preview.insert('1.0', TEST_MESSAGE)
        preview.configure(state='disabled')
        preview.grid(row=2, column=0, sticky='nsew')
        preview_scroll = ttk.Scrollbar(test_tab, orient='vertical', command=preview.yview)
        preview.configure(yscrollcommand=preview_scroll.set)
        preview_scroll.grid(row=2, column=1, sticky='ns')
        self.machine = tk.StringVar()
        try:
            self.machine.set(get_machine_id())
        except ValueError:
            self.machine.set('MACHINE_ID_UNAVAILABLE')
        ttk.Label(test_tab, text='Machine ID สำหรับรายการอนุมัติ (อ่านในเครื่องเท่านั้น):').grid(row=3, column=0, columnspan=2, sticky='w', pady=(14, 4))
        ttk.Entry(test_tab, textvariable=self.machine, state='readonly', width=72).grid(row=4, column=0, columnspan=2, sticky='w')
        self.test_status = tk.StringVar()
        ttk.Label(test_tab, textvariable=self.test_status, wraplength=850).grid(row=5, column=0, columnspan=2, sticky='ew', pady=12)
        self.confirm_test = tk.BooleanVar(value=False)
        ttk.Checkbutton(test_tab, text='ยืนยันส่ง TEST จำลองจากเครื่องและผู้รับที่ได้รับอนุมัติในครั้งนี้',
                        variable=self.confirm_test, command=self.refresh_test).grid(row=6, column=0, columnspan=2, sticky='w')
        test_actions = ttk.Frame(test_tab)
        test_actions.grid(row=7, column=0, columnspan=2, sticky='ew', pady=10)
        ttk.Button(test_actions, text='พรีวิว dry-run / ตรวจเงื่อนไข', command=self.refresh_test).pack(side='left', padx=(0, 10))
        self.send_button = ttk.Button(test_actions, text='ส่ง Telegram TEST', command=self.send_test, state='disabled')
        self.send_button.pack(side='left')
        ttk.Label(body, text='ขอบเขต PoC: ไม่เชื่อม WinCC/PLC • ไม่อ่านระบบ Live • ไม่พร้อม Production',
                  foreground='#52636b').grid(row=3, column=0, sticky='ew', pady=(12, 0))
        self.refresh_test()

    def _error(self, error):
        messagebox.showerror('หยุดทำรายการ', str(error) if isinstance(error, (ValueError, LedgerError)) else 'LOCAL_FILE_ERROR')

    def load_demo(self):
        try:
            self.session.open_bytes(demo_csv(), 'DEMO_CURRENT.csv')
            self.refresh()
        except HANDLED as error:
            self._error(error)

    def choose_file(self):
        path = filedialog.askopenfilename(title='เลือกไฟล์ที่ส่งออกโดยผู้ได้รับอนุญาต', filetypes=[('TXT / CSV', '*.txt *.csv'), ('TXT', '*.txt'), ('CSV', '*.csv')])
        if not path:
            return
        try:
            self.session.open_file(path)
            self.refresh()
        except HANDLED as error:
            self._clear()
            self._error(error)

    def choose_profile(self):
        path = filedialog.askopenfilename(title='เลือกโปรไฟล์ที่ไม่มี token', filetypes=[('Policy JSON', '*.json')])
        if not path:
            return
        self.confirm_test.set(False)
        self.refresh_test()
        try:
            self.session.select_profile(path)
            self._clear()
            self.profile_label.configure(text='Profile: ' + self.session.profile.profile_id)
            self.refresh_test()
        except HANDLED as error:
            self._clear()
            self._error(error)

    def _clear(self):
        self.table.delete(*self.table.get_children())
        self.rows_shown = []
        self.summary.set('ยังไม่มีผลพรีวิว — เลือกไฟล์หรือข้อมูลจำลองใหม่')
        self.file_info.set('เลือกเฉพาะไฟล์ในเครื่องที่ได้รับอนุญาต')
        self.export_button.state(['disabled'])
        self.commit_button.state(['disabled'])

    def _render(self, rows):
        self._clear()
        self.rows_shown = rows[:2000]
        source = self.session.source
        self.file_info.set(f'{source.name}  |  {source.encoding}  |  {source.kind}\nSHA-256: {source.sha256}')
        if source.kind == 'tag_configuration':
            self.summary.set('Tag Configuration เท่านั้น — ไม่มีข้อมูลสถานะจริง จึงไม่สร้าง ON/OFF หรือแจ้งเตือน')
            return
        if source.kind != 'runtime_values':
            self.summary.set('ไม่รู้จักรูปแบบหัวตาราง — ไม่เดาสถานะ กรุณาดู schema ที่รองรับใน README')
            return
        counts = Counter(item.state for item in rows)
        candidates = sum(item.decision == 'CANDIDATE' for item in rows)
        checked = datetime.now(timezone.utc).astimezone().strftime('%H:%M:%S %z')
        self.summary.set(f'ON {counts["ON"]}   /   OFF {counts["OFF"]}   /   UNKNOWN {counts["UNKNOWN"]}   /   ERROR {counts["ERROR"]}'
                         f'    •    เข้าเกณฑ์ dry-run {candidates}    •    ประเมิน {checked}\n'
                         f'แสดง {min(len(rows), 2000)} / {len(rows)} แถว — Export ครบทุกแถว — ค่าจากไฟล์ ณ เวลาที่ระบุ')
        for index, item in enumerate(self.rows_shown):
            reason = ' / '.join(REASONS_TH.get(r, r) for r in item.reasons) or 'ผ่านเกณฑ์'
            values = (item.raw.source_row, item.raw.tag, item.raw.timestamp_raw, item.raw.value_raw,
                      item.raw.quality_raw, item.state, DECISIONS_TH.get(item.decision, item.decision), reason)
            self.table.insert('', 'end', iid=str(index), values=values, tags=(item.state,))
        self.export_button.state(['!disabled'])
        self.commit_button.state(['!disabled'])

    def refresh(self):
        if self.session.source is None:
            self._clear()
            return
        try:
            self._render(self.session.rows())
        except HANDLED as error:
            self._clear()
            self._error(error)

    def export_file(self):
        if self.session.source is None:
            return
        target = filedialog.asksaveasfilename(title='สร้างไฟล์ใหม่ — ไม่เขียนทับไฟล์เดิม', defaultextension='.csv',
                                             initialfile='aqua_structured.csv', filetypes=[('Structured CSV', '*.csv')], confirmoverwrite=False)
        if not target:
            return
        try:
            _, rows = self.session.export(target)
            self._render(rows)
            messagebox.showinfo('Export สำเร็จ', 'สร้าง structured CSV แล้ว\nไฟล์ต้นฉบับคงเดิม; ไม่มีการส่ง Telegram')
        except HANDLED as error:
            self._error(error)

    def commit_dry_run(self):
        if self.session.source is None:
            return
        try:
            rows = self.session.rows(commit=True)
            self._render(rows)
            messagebox.showinfo('Dry-run', 'บันทึกประวัติ dry-run ในเครื่องแล้ว\nไม่มีการส่ง Telegram; เปิดไฟล์เดิมอีกครั้งจะตรวจพบรายการซ้ำ')
        except HANDLED as error:
            self._error(error)

    def show_details(self, _event=None):
        selected = self.table.selection()
        if not selected:
            return
        item = self.rows_shown[int(selected[0])]
        messagebox.showinfo('รายละเอียด sample จากไฟล์',
                            f'Tag: {item.raw.tag}\nTimestamp: {item.raw.timestamp_raw}\nValue: {item.raw.value_raw}\n'
                            f'Quality: {item.raw.quality_raw}\nState: {item.state}\n'
                            f'Reason: {", ".join(item.reasons) or "OK"}\nDecision: {item.decision}\n'
                            f'Age: {item.age_seconds} seconds\nDRY_RUN / ไม่ใช่สถานะ Live')

    def refresh_test(self):
        reasons = readiness(self.session.profile)
        self.test_status.set('DRY-RUN • ยังไม่มีการส่ง\n' + ('เงื่อนไขที่ยังไม่ผ่าน: ' + ', '.join(reasons) if reasons else 'ผ่านเงื่อนไขในโปรไฟล์ — ต้องยืนยัน TEST ครั้งนี้ก่อนส่ง'))
        enabled = not reasons and self.confirm_test.get() and not self.test_running
        self.send_button.state(['!disabled'] if enabled else ['disabled'])

    def send_test(self):
        if self.test_running or not self.confirm_test.get():
            return
        self.test_running = True
        self.send_button.state(['disabled'])
        profile = self.session.profile
        self.confirm_test.set(False)
        self.test_status.set('กำลังส่ง TEST จำลอง — ไม่อ่านหรือส่งข้อมูลจากไฟล์')
        def work():
            try:
                with Ledger(self.session.ledger_path) as ledger:
                    result = run_test(profile, ledger, send=True, confirmed=True)
                self.results.put(result.outcome + ' | ' + ', '.join(result.reasons))
            except HANDLED:
                self.results.put('BLOCKED | LEDGER_OR_LOCAL_CONFIGURATION_ERROR')
        threading.Thread(target=work, daemon=True).start()
        self.root.after(100, self._receive_test_result)

    def _receive_test_result(self):
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self._receive_test_result)
            return
        self.test_running = False
        self.test_status.set(result)
        self.send_button.state(['disabled'])


def launch(config_path=None, data_dir=None):
    session = Session(config_path, data_dir)
    try:
        root = tk.Tk()
    except tk.TclError:
        raise ValueError('GUI_DISPLAY_UNAVAILABLE_USE_CLI_OR_WINDOWS_DESKTOP') from None
    App(root, session)
    root.mainloop()
    return 0
