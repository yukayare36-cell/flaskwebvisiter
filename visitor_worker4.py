import os
import subprocess
import sys

def run_command(command, cwd=None):
    """Run a shell command and return the output"""
    try:
        result = subprocess.run(command, shell=True, cwd=cwd, check=True, 
                              capture_output=True, text=True)
        print(f"✅ Command succeeded: {command}")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {command}")
        print(f"Error: {e.stderr}")
        return False

def main():
    # 1. Clone the repository
    repo_url = "https://github.com/yukayare36-cell/1.git"
    print(f"Cloning repository: {repo_url}")
    
    if not run_command(f"git clone {repo_url}"):
        sys.exit(1)
    
    # 2. Move into the directory
    repo_dir = "1"
    print(f"Changing directory to: {repo_dir}")
    
    # Check if directory exists
    if not os.path.exists(repo_dir):
        print(f"❌ Directory '{repo_dir}' not found after cloning")
        sys.exit(1)
    
    # 3. Make the file executable
    # Note: The command should be "chmod +x 1" (assuming the file is named "1")
    # This is correct if there's a file named "1" in the directory
    print("Making file '1' executable...")
    if not run_command("chmod +x 1", cwd=repo_dir):
        sys.exit(1)
    
    # 4. Run the executable
    print("Running ./1...")
    print("-" * 50)
    if not run_command("./1", cwd=repo_dir):
        sys.exit(1)
    print("-" * 50)

if __name__ == "__main__":
    main()
