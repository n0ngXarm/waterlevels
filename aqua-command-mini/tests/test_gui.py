"""Optional real Tk widget/callback test. Enable only on a graphical test machine."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(os.environ.get('AQUA_RUN_GUI_TESTS') == '1', 'requires graphical display; set AQUA_RUN_GUI_TESTS=1')
class GuiTests(unittest.TestCase):
    def test_demo_export_and_configuration_callbacks(self):
        import tkinter as tk
        from aqua_command.gui import App
        from aqua_command.session import Session
        with tempfile.TemporaryDirectory() as tmp:
            root = tk.Tk()
            root.withdraw()
            self.addCleanup(root.destroy)
            app = App(root, Session(data_dir=Path(tmp) / 'state'))
            app.load_demo()
            root.update_idletasks()
            root.deiconify()
            root.geometry('1240x760+0+0')
            root.update()
            self.assertTrue(app.export_button.winfo_ismapped(), 'Export button must remain visible')
            self.assertLessEqual(app.export_button.winfo_rooty() + app.export_button.winfo_height(),
                                 root.winfo_rooty() + root.winfo_height())
            test_tab = app.send_button.master.master
            notebook = test_tab.master
            notebook.select(test_tab)
            root.geometry('940x620+0+0')
            root.update()
            self.assertTrue(app.send_button.winfo_ismapped(), 'TEST controls must remain visible at minimum size')
            self.assertLessEqual(app.send_button.winfo_rooty() + app.send_button.winfo_height(),
                                 root.winfo_rooty() + root.winfo_height())
            notebook.select(app.table.master.master)
            root.geometry('1240x760+0+0')
            root.update()
            self.assertEqual(len(app.table.get_children()), 2)
            self.assertEqual([app.table.item(i)['values'][5] for i in app.table.get_children()], ['ON', 'OFF'])
            target = Path(tmp) / 'structured.csv'
            with patch('aqua_command.gui.filedialog.asksaveasfilename', return_value=str(target)), patch('aqua_command.gui.messagebox.showinfo'):
                app.export_file()
            self.assertTrue(target.exists())
            config = Path(tmp) / 'config.txt'
            config.write_text('DmTag\tTags\tTag', encoding='utf-16')
            with patch('aqua_command.gui.filedialog.askopenfilename', return_value=str(config)):
                app.choose_file()
            self.assertEqual(len(app.table.get_children()), 0)
            self.assertIn('Tag Configuration', app.summary.get())
            self.assertTrue(app.send_button.instate(['disabled']))
