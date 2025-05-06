def scan_for_duplicates(selected_disks):
    """Scan the selected drives for duplicates and calculate metrics."""
    min_size = 0
    ext_filter = []
    keep_strategy = "newest"

    # Fixed output directory
    scan_output_dir = "/output/scan_results"
    os.makedirs(scan_output_dir, exist_ok=True)

    file_index = {}
    total_files = sum(len(files) for disk in selected_disks for _, _, files in os.walk(disk))
    total_duplicate_files = 0
    total_duplicate_size = 0
    disks_with_duplicates = set()

    with tqdm(total=total_files, desc="Scanning files", unit="file") as pbar:
        for disk in selected_disks:
            for root, _, files in os.walk(disk):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        if min_size and os.path.getsize(file_path) < min_size:
                            pbar.update(1)
                            continue
                        if ext_filter and not file.endswith(tuple(ext_filter)):
                            pbar.update(1)
                            continue

                        rel_path = os.path.relpath(file_path, disk)
                        file_index.setdefault(rel_path, []).append(file_path)
                    except Exception as e:
                        print(f"Error processing {file_path}: {e}")
                    finally:
                        pbar.update(1)

    csv_file = Path(scan_output_dir) / f"duplicates_{SESSION_TIMESTAMP}.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Group", "Relative Path", "Full Path", "Modification Time", "Size", "Keep"])
        group_id = 1
        for rel_path, paths in file_index.items():
            if len(paths) > 1:
                # Determine which file to keep based on the keep_strategy
                if keep_strategy == "newest":
                    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                elif keep_strategy == "oldest":
                    paths.sort(key=lambda p: os.path.getmtime(p))
                elif keep_strategy == "largest":
                    paths.sort(key=lambda p: os.path.getsize(p), reverse=True)
                elif keep_strategy == "smallest":
                    paths.sort(key=lambda p: os.path.getsize(p))

                # Update metrics
                total_duplicate_files += len(paths) - 1  # Exclude the "keep" file
                total_duplicate_size += sum(os.path.getsize(p) for p in paths[1:])  # Size of extra files
                disks_with_duplicates.update(os.path.dirname(p).split("/")[2] for p in paths)  # Extract disk names

                # Write the results to the CSV
                for path in paths:
                    mod_time = os.path.getmtime(path)
                    size = os.path.getsize(path)
                    keep = "yes" if path == paths[0] else "no"
                    writer.writerow([group_id, rel_path, path, mod_time, size, keep])
                group_id += 1

    print(f"✅ Duplicate detection complete. Results saved to: {csv_file}")
    return {
        "csv_file": str(csv_file),
        "total_duplicates": total_duplicate_files,
        "disks_with_duplicates": list(disks_with_duplicates),
        "total_duplicate_size": total_duplicate_size,
        from flask import current_app

        def scan_for_duplicates(selected_disks):
            """Scan the selected drives for duplicates and update progress."""
            min_size = 0
            ext_filter = []
            keep_strategy = "newest"

            # Fixed output directory
            scan_output_dir = "/output/scan_results"
            os.makedirs(scan_output_dir, exist_ok=True)

            file_index = {}
            total_files = sum(len(files) for disk in selected_disks for _, _, files in os.walk(disk))
            current_app.config["SCAN_PROGRESS"] = 0  # Initialize progress

            with tqdm(total=total_files, desc="Scanning files", unit="file") as pbar:
                for disk in selected_disks:
                    for root, _, files in os.walk(disk):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                if min_size and os.path.getsize(file_path) < min_size:
                                    pbar.update(1)
                                    current_app.config["SCAN_PROGRESS"] += 1
                                    continue
                                if ext_filter and not file.endswith(tuple(ext_filter)):
                                    pbar.update(1)
                                    current_app.config["SCAN_PROGRESS"] += 1
                                    continue

                                rel_path = os.path.relpath(file_path, disk)
                                file_index.setdefault(rel_path, []).append(file_path)
                            except Exception as e:
                                print(f"Error processing {file_path}: {e}")
                            finally:
                                pbar.update(1)
                                current_app.config["SCAN_PROGRESS"] += 1

            # Reset progress after completion
            current_app.config["SCAN_PROGRESS"] = 100
            return {
                "csv_file": str(csv_file),
                "total_duplicates": total_duplicate_files,
                "disks_with_duplicates": list(disks_with_duplicates),
                "total_duplicate_size": total_duplicate_size,
            }
    }
