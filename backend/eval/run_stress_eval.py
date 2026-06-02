import subprocess
import sys
from pathlib import Path

def main():
    backend_dir = Path(__file__).resolve().parents[1]
    eval_script = backend_dir / "eval" / "run_eval.py"
    stress_json = backend_dir / "eval" / "stress_queries_1000.json"
    
    cmd = [sys.executable, str(eval_script), "--gold-set", str(stress_json)] + sys.argv[1:]
    
    print(f"Running stress eval: {' '.join(cmd)}")
    subprocess.run(cmd)

if __name__ == "__main__":
    main()
