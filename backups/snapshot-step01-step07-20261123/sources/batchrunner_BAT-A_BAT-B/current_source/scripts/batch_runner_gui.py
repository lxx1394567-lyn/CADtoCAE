import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from cadtocae.batch_runner.gui import main
if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-json':
        import json
        import tkinter as tk
        from cadtocae.batch_runner.gui import BatchRunnerGUI
        from cadtocae.batch_runner import cae_worker_source
        root = tk.Tk()
        root.withdraw()
        gui = BatchRunnerGUI(root)
        root.update()
        Path(sys.argv[2]).write_text(json.dumps({'status':'PASS','tk':tk.TkVersion,'worker_bytes':len(cae_worker_source())}), encoding='utf-8')
        root.destroy()
    else:
        main()
