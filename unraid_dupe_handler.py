import os
import sys
import csv
from datetime import datetime
from pathlib import Path

# Constants
CONFIG_PATH = Path(__file__).parent / "dupe_config.conf"
SESSION_TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
DEFAULT_KEEP_STRATEGY = "newest"

# Global variables
config = {}
selected_disks = []
keep_strategy = DEFAULT_KEEP_STRATEGY


def load_config():
    """Load configuration from the config file."""
    global config
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            for line in f:
                key, value = line.strip().split("=", 1)
                config[key] = value


def save_config():
    """Save configuration to the config file."""
    with open(CONFIG_PATH, "w") as f:
        for key, value in config.items():
            f.write(f"{key}={value}\n")


def prompt_path(prompt_text, saved_var, default_path):
    """Prompt the user for a directory path."""
    saved_path = config.get(saved_var, "")
    if saved_path:
        use_saved = input(f"Use saved {prompt_text} directory '{saved_path}'? (y/n): ").strip().lower()
        if use_saved in ("y", "yes", ""):
            return saved_path

    user_input = input(f"Enter directory to save {prompt_text} (default: {default_path}): ").strip()
    result_path = user_input or default_path
    os.makedirs(result_path, exist_ok=True)
    config[saved_var] = result_path
    return result_path


def scan_for_duplicates():
    """Scan for duplicate files based on relative paths across disks."""
    global selected_disks, keep_strategy

    scan_output_dir = prompt_path("scan output", "scan_output_dir", str(Path(__file__).parent))
    log_output_dir = prompt_path("log file", "log_output_dir", str(Path(__file__).parent))
    save_config()

    # Select disks
    print("1) Array only\n2) Pool only\n3) Both Array and Pool")
    source_choice = input("Choose an option [1-3, default 1]: ").strip() or "1"

    if source_choice in ("1", "3"):
        array_disks = [str(p) for p in Path("/mnt").glob("disk*") if "disks" not in str(p)]
        print("🥮 Available array disks:")
        for i, disk in enumerate(array_disks, 1):
            print(f"{i}) {disk}")
        selected_disks.extend(array_disks)

    if source_choice in ("2", "3"):
        pool_disks = [str(p) for p in Path("/mnt").glob("*pool*")]
        print("🥮 Available pool disks:")
        for i, disk in enumerate(pool_disks, 1):
            print(f"{i}) {disk}")
        selected_disks.extend(pool_disks)

    # Filters
    min_size = input("Enter minimum file size in bytes (or leave blank): ").strip()
    ext_filter = input("Enter file extensions to include (comma-separated, or leave blank): ").strip()

    # Keep strategy
    print("📌 Choose how to select the 'Keep' file in each duplicate group:")
    print("1) Newest file (default)\n2) Oldest file\n3) Largest file\n4) Smallest file")
    keep_choice = input("Enter choice [1-4, default: 1]: ").strip() or "1"
    keep_strategy = {
        "1": "newest",
        "2": "oldest",
        "3": "largest",
        "4": "smallest"
    }.get(keep_choice, "newest")

    # Scan for duplicates
    print("🔍 Scanning selected disks...")
    file_index = {}
    for disk in selected_disks:
        for root, _, files in os.walk(disk):
            for file in files:
                file_path = os.path.join(root, file)
                if min_size and os.path.getsize(file_path) < int(min_size):
                    continue
                if ext_filter and not file.endswith(tuple(ext_filter.split(","))):
                    continue

                # Get the relative path of the file
                rel_path = os.path.relpath(file_path, disk)
                if rel_path not in file_index:
                    file_index[rel_path] = []
                file_index[rel_path].append(file_path)

    # Save results to CSV
    csv_file = Path(scan_output_dir) / f"duplicates_{SESSION_TIMESTAMP}.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Group", "Relative Path", "Full Path", "Modification Time", "Size", "Keep"])
        group_id = 1
        for rel_path, paths in file_index.items():
            if len(paths) > 1:  # Only consider duplicates
                for path in paths:
                    mod_time = os.path.getmtime(path)
                    size = os.path.getsize(path)
                    keep = "yes" if path == paths[0] else "no"
                    writer.writerow([group_id, rel_path, path, mod_time, size, keep])
                group_id += 1

    print(f"✅ Duplicate detection complete. Results saved to: {csv_file}")


def main():
    """Main menu."""
    load_config()
    while True:
        print("\n🧾 Unraid Duplicate File Handler")
        print("1) Scan for duplicate files")
        print("2) Exit")
        choice = input("Choose an option [1-2]: ").strip()
        if choice == "1":
            scan_for_duplicates()
        elif choice == "2":
            print("👋 Exiting. Goodbye!")
            sys.exit(0)
        else:
            print("❌ Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
