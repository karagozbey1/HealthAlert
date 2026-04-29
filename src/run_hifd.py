import subprocess
import sys
from pathlib import Path

def main():
    root = Path(__file__).resolve().parents[1]
    script = root / "src" / "train_hifd_crnn_mat.py"
    subprocess.check_call([sys.executable, str(script), "--data_root", r"Data\HIFD"], cwd=str(root))

if __name__ == "__main__":
    main()
