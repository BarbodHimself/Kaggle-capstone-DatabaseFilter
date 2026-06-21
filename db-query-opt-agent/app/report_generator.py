import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

def generate_report():
    """Generates a markdown summary report from evaluation results and run history."""
    project_root = Path(__file__).resolve().parent.parent
    eval_file = project_root / "eval_results.json"
    history_file = project_root / "app" / "run_history.jsonl"
    reports_dir = project_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "summary_report.md"

    # 1. Title with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_lines = [
        f"# Database Optimizer Summary Report",
        f"**Generated:** {timestamp}\n",
    ]

    # Load eval results
    eval_data: Dict[str, Any] = {}
    if eval_file.exists():
        try:
            with open(eval_file, "r") as f:
                eval_data = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load {eval_file}: {e}")

    # 2. Evaluation Summary
    report_lines.append("## Evaluation Summary\n")
    if eval_data:
        acc = eval_data.get("overall_accuracy", 0.0)
        lat = eval_data.get("average_latency", 0.0)
        report_lines.append(f"- **Overall Accuracy**: {acc:.2f}%")
        report_lines.append(f"- **Average Latency**: {lat:.4f} seconds\n")

        cat_stats = eval_data.get("category_stats", {})
        if cat_stats:
            report_lines.append("| Category | Accuracy | Correct / Total |")
            report_lines.append("|---|---|---|")
            for cat, stats in cat_stats.items():
                total = stats.get("total", 0)
                correct = stats.get("correct", 0)
                cat_acc = (correct / total * 100) if total > 0 else 0
                report_lines.append(f"| {cat} | {cat_acc:.2f}% | {correct} / {total} |")
        report_lines.append("\n")
    else:
        report_lines.append("*No evaluation results found. Run `uv run python app/eval_agent.py` to generate them.*\n")

    # 3. Known Gaps
    report_lines.append("## Known Gaps\n")
    gaps_found = []
    if eval_data:
        cat_stats = eval_data.get("category_stats", {})
        for cat, stats in cat_stats.items():
            total = stats.get("total", 0)
            correct = stats.get("correct", 0)
            cat_acc = (correct / total * 100) if total > 0 else 0
            if cat_acc < 100.0:
                gaps_found.append((cat, cat_acc))
                
    if gaps_found:
        for cat, cat_acc in gaps_found:
            report_lines.append(f"- **{cat}**: {cat_acc:.2f}% accuracy. The agent failed to correctly process some queries in this category.")
    else:
        if eval_data:
            report_lines.append("*No known gaps! All categories passed with 100% accuracy.*")
        else:
            report_lines.append("*Cannot determine gaps without evaluation data.*")
    report_lines.append("\n")

    # 4. Sample Optimizer Reasoning
    report_lines.append("## Sample Optimizer Reasoning\n")
    reasoning_samples = []
    if history_file.exists():
        try:
            with open(history_file, "r") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        logs = record.get("session_logs", [])
                        for log in reversed(logs):
                            if log.startswith("Optimizer reasoning: "):
                                reasoning_samples.append(log[len("Optimizer reasoning: "):])
                                break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Warning: Failed to read {history_file}: {e}")

    # De-duplicate and take up to 5
    unique_samples = list(dict.fromkeys(reasoning_samples))
    samples_to_show = unique_samples[:5]
    
    if samples_to_show:
        for s in samples_to_show:
            report_lines.append(f"- {s}")
    else:
        report_lines.append("*No optimizer reasoning samples available. Run some successful queries first.*")
    report_lines.append("\n")

    # 5. Recommendations
    report_lines.append("## Recommendations\n")
    if gaps_found:
        for cat, _ in gaps_found:
            report_lines.append(f"- Investigate why `{cat}` accuracy is below 100% and update the sanitization or optimization logic accordingly.")
        report_lines.append("- Add more test cases to the evaluation harness to cover edge cases within these failing categories.")
    elif eval_data:
        report_lines.append("- Maintain current logic as all categories are performing at 100%.")
        report_lines.append("- Consider adding new categories or more complex queries to test the limits of the optimizer.")
    else:
        report_lines.append("- Run the evaluation harness to identify potential gaps in the system.")
        report_lines.append("- Test the agent with realistic workloads to generate run history.")
    
    report_lines.append("\n")

    with open(report_path, "w") as f:
        f.write("\n".join(report_lines))

    print(f"Report generated successfully: {report_path.absolute()}")

if __name__ == "__main__":
    generate_report()
