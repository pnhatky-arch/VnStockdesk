from pathlib import Path
import sys
import pandas as pd
from src.data_jobs import DataJobs, discover_tasks, perform_task
from src.local_io import atomic_json
from scan import output_paths


if __name__ == "__main__":
    manager = DataJobs(Path(sys.argv[1]))
    job = manager.run(discover_tasks, perform_task)
    rows = list(job.get("analysis", {}).values())
    if rows:
        # A partial attempt never replaces an existing complete scanner file.
        target = output_paths(job["scope"])[0] if job["status"] == "COMPLETE" else manager.directory / "partial_analysis.csv"
        temporary = target.with_suffix(".init.tmp")
        pd.DataFrame(rows).to_csv(temporary, index=False)
        temporary.replace(target)
        if job["status"] == "COMPLETE":
            atomic_json(output_paths(job["scope"])[2], {"scope":job["scope"],"generated_at":pd.Timestamp.now().isoformat(),"analyzed":len(rows),"universe":len(rows),"errors":0,"source":"data_initialization"})
