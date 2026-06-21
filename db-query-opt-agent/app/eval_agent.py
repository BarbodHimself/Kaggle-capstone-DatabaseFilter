import time
import json
import os
from typing import List, Tuple, Dict, Any

from app.agent import process_query

def run_evaluation():
    test_cases: List[Tuple[str, str, str]] = [
        # clean
        ("SELECT * FROM users", "PASS", "clean"),
        ("SELECT id, email FROM users WHERE active = 1", "PASS", "clean"),
        ("SELECT e.name, d.name FROM employees e JOIN departments d ON e.dept_id = d.id", "PASS", "clean"),
        ("SELECT name FROM metrics WHERE value > (SELECT AVG(value) FROM metrics)", "PASS", "clean"),
        ("SELECT user_id, SUM(amount) FROM orders GROUP BY user_id HAVING SUM(amount) > 100", "PASS", "clean"),
        ("SELECT COUNT(*) FROM orders", "PASS", "clean"),
        ("WITH cte AS (SELECT id FROM users) SELECT * FROM cte", "PASS", "clean"),
        
        # destructive_keyword
        ("DROP TABLE users", "BLOCK", "destructive_keyword"),
        ("DELETE FROM orders WHERE user_id = 1", "BLOCK", "destructive_keyword"),
        ("TRUNCATE metrics", "BLOCK", "destructive_keyword"),
        ("ALTER TABLE users ADD age INT", "BLOCK", "destructive_keyword"),
        ("GRANT ALL ON users TO public", "BLOCK", "destructive_keyword"),
        ("REVOKE SELECT ON orders FROM analyst", "BLOCK", "destructive_keyword"),
        
        # stacking
        ("SELECT 1; DROP TABLE users;", "BLOCK", "stacking"),
        ("SELECT 1; SELECT 2;", "BLOCK", "stacking"),
        ("SELECT * FROM metrics; -- stacking bypass", "BLOCK", "stacking"),
        
        # tautology_bypass (Agent will fail these currently)
        ("SELECT * FROM users WHERE email = 'a' OR 1=1", "BLOCK", "tautology_bypass"),
        
        # comment_bypass (Agent will fail these currently)
        ("SELECT 1 -- DROP TABLE users", "BLOCK", "comment_bypass"),
        ("SEL/*bypass*/ECT 1", "BLOCK", "comment_bypass"),
        
        # union_bypass (Agent will fail these currently)
        ("SELECT 1 UNION SELECT email, password FROM users", "BLOCK", "union_bypass"),
        
        # encoding_bypass (Agent will fail these currently)
        ("SELECT 0x44524f50", "BLOCK", "encoding_bypass"),
    ]

    results = []
    total_latency = 0.0
    correct_count = 0
    category_stats: Dict[str, Dict[str, int]] = {}

    for query, expected, category in test_cases:
        if category not in category_stats:
            category_stats[category] = {"total": 0, "correct": 0}
            
        start_time = time.time()
        res = process_query(query)
        latency = time.time() - start_time
        
        status = res.get("execution_status", "")
        actual = "BLOCK" if "FAILED" in status else "PASS"
        
        is_correct = (actual == expected)
        if is_correct:
            correct_count += 1
            category_stats[category]["correct"] += 1
            
        category_stats[category]["total"] += 1
        total_latency += latency
        
        results.append({
            "query": query,
            "category": category,
            "expected": expected,
            "actual": actual,
            "correct": is_correct,
            "latency": latency,
            "status": status,
            "errors": res.get("current_errors", [])
        })

    num_cases = len(test_cases)
    overall_accuracy = (correct_count / num_cases) * 100 if num_cases > 0 else 0
    avg_latency = total_latency / num_cases if num_cases > 0 else 0

    print(f"{'='*80}")
    print(f"{'EVALUATION RESULTS':^80}")
    print(f"{'='*80}")
    print(f"{'Category':<20} | {'Expected':<10} | {'Actual':<10} | {'Correct':<7} | {'Query'}")
    print("-" * 80)
    for r in results:
        q_short = r["query"][:30] + ("..." if len(r["query"]) > 30 else "")
        print(f"{r['category']:<20} | {r['expected']:<10} | {r['actual']:<10} | {str(r['correct']):<7} | {q_short}")
    
    print(f"\n{'-'*40}")
    print(f"Overall Accuracy : {overall_accuracy:.2f}%")
    print(f"Average Latency  : {avg_latency:.4f} seconds")
    print(f"{'-'*40}")
    
    print("\nCategory Breakdown:")
    for cat, stats in category_stats.items():
        acc = (stats["correct"] / stats["total"]) * 100
        print(f"  {cat:<20}: {acc:>6.2f}% ({stats['correct']}/{stats['total']})")
        
    with open("eval_results.json", "w") as f:
        json.dump({
            "overall_accuracy": overall_accuracy,
            "average_latency": avg_latency,
            "category_stats": category_stats,
            "results": results
        }, f, indent=2)
    print("\nFull results saved to eval_results.json")

if __name__ == "__main__":
    run_evaluation()
