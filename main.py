import subprocess
import sys

def run_script(script_name):
    """Run a Python script and check for errors."""
    print(f"Running {script_name}...")
    result = subprocess.run([sys.executable, script_name])
    if result.returncode != 0:
        print(f"Error in {script_name}: Script failed with return code {result.returncode}")
        sys.exit(1)
    else:
        print(f"{script_name} completed successfully.")

def main():
    # List of scripts to run in sequence
    scripts = [
        # "1-SECFilingsDownloader.py",
        "2-SECFilingTextExtractor.py",
        "3-SECFilingParagraphExtractor.py",
        "4-LLMCompetitorExtractor.py",
        "5-map.py"
    ]
    
    for script in scripts:
        run_script(script)
    
    print("All scripts executed successfully!")

if __name__ == "__main__":
    main()