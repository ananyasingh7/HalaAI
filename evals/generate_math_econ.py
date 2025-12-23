import json
import argparse
import os
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVALS_DIR.parent
DEFAULT_OUTPUT_PATH = Path(os.environ.get("HALA_EVAL_DATASET_OUT", str(EVALS_DIR / "datasets" / "golden_general.jsonl")))

# The 50 Questions (Math, Economics, Logic)
questions = [
    # --- MATH (Calculus, Probability, Algebra) ---
    {"category": "math", "question": "Calculate the derivative of f(x) = x^3 - 2x + 4.", "expected_keyword": "3x^2"},
    {"category": "math", "question": "What is the probability of flipping 3 heads in a row with a fair coin?", "expected_keyword": "1/8"},
    {"category": "math", "question": "Solve for x: 2x + 5 = 15.", "expected_keyword": "5"},
    {"category": "math", "question": "What is the integral of 1/x?", "expected_keyword": "ln(|x|)"},
    {"category": "math", "question": "What is the square root of 144?", "expected_keyword": "12"},
    {"category": "math", "question": "If a vector v = (3, 4), what is its magnitude?", "expected_keyword": "5"},
    {"category": "math", "question": "Convert 45 degrees to radians.", "expected_keyword": "pi/4"},
    {"category": "math", "question": "What is the value of e^(ln 5)?", "expected_keyword": "5"},
    {"category": "math", "question": "Solve the system: x + y = 10, x - y = 2.", "expected_keyword": "6"},
    {"category": "math", "question": "What is the sum of angles in a triangle?", "expected_keyword": "180"},
    {"category": "math", "question": "Calculate 15% of 80.", "expected_keyword": "12"},
    {"category": "math", "question": "What is the factorial of 5?", "expected_keyword": "120"},
    {"category": "math", "question": "If f(x) = sin(x), what is f'(x)?", "expected_keyword": "cos"},
    {"category": "math", "question": "Log base 2 of 32 is?", "expected_keyword": "5"},
    {"category": "math", "question": "What is the area of a circle with radius 3?", "expected_keyword": "9pi"},
    
    # --- ECONOMICS (Micro, Macro, Game Theory) ---
    {"category": "econ", "question": "Explain the concept of Opportunity Cost.", "expected_keyword": "foregone"},
    {"category": "econ", "question": "What happens to price when demand exceeds supply?", "expected_keyword": "increase"},
    {"category": "econ", "question": "Define 'Nash Equilibrium' in simple terms.", "expected_keyword": "strategy"},
    {"category": "econ", "question": "What is the difference between nominal and real GDP?", "expected_keyword": "inflation"},
    {"category": "econ", "question": "What is a 'Giffen Good'?", "expected_keyword": "demand"},
    {"category": "econ", "question": "Explain the law of diminishing returns.", "expected_keyword": "marginal"},
    {"category": "econ", "question": "What role does the Central Bank play in an economy?", "expected_keyword": "interest"},
    {"category": "econ", "question": "What is a monopoly?", "expected_keyword": "single"},
    {"category": "econ", "question": "Define 'elasticity of demand'.", "expected_keyword": "sensitivity"},
    {"category": "econ", "question": "What is a sunk cost?", "expected_keyword": "recover"},
    {"category": "econ", "question": "Explain 'comparative advantage' in trade.", "expected_keyword": "efficiency"},
    {"category": "econ", "question": "What is inflation?", "expected_keyword": "prices"},
    {"category": "econ", "question": "What is the invisible hand theory?", "expected_keyword": "Smith"},
    {"category": "econ", "question": "Describe a 'bear market'.", "expected_keyword": "decline"},
    {"category": "econ", "question": "What is fiat money?", "expected_keyword": "government"},

    # --- LOGIC (Coding, Riddles, Reasoning) ---
    {"category": "logic", "question": "If all A are B, and some B are C, are all A definitely C?", "expected_keyword": "No"},
    {"category": "logic", "question": "Write a Python function to reverse a string.", "expected_keyword": "return"},
    {"category": "logic", "question": "I have keys but no locks. I have a space but no room. You can enter, but never go outside. What am I?", "expected_keyword": "keyboard"},
    {"category": "logic", "question": "If it rains, the ground is wet. The ground is wet. Did it rain?", "expected_keyword": "necessarily"},
    {"category": "logic", "question": "Which is heavier: a pound of lead or a pound of feathers?", "expected_keyword": "same"},
    {"category": "logic", "question": "Identify the pattern: 2, 4, 8, 16, ...", "expected_keyword": "32"},
    {"category": "logic", "question": "Write a SQL query to select all users named 'Alice'.", "expected_keyword": "SELECT"},
    {"category": "logic", "question": "If you pass the person in 2nd place in a race, what place are you in?", "expected_keyword": "2nd"},
    {"category": "logic", "question": "A is the father of B. B is the father of C. What is A to C?", "expected_keyword": "grandfather"},
    {"category": "logic", "question": "Code a loop in Python that prints numbers 1 to 5.", "expected_keyword": "range"},
    {"category": "logic", "question": "Does correlation imply causation?", "expected_keyword": "No"},
    {"category": "logic", "question": "What comes next: J, F, M, A, M, J, ...?", "expected_keyword": "J"},
    {"category": "logic", "question": "True or False: NOT(True AND False)", "expected_keyword": "True"},
    {"category": "logic", "question": "Explain the concept of recursion.", "expected_keyword": "itself"},
    {"category": "logic", "question": "What is the difference between a list and a set in Python?", "expected_keyword": "duplicate"},
    {"category": "logic", "question": "If 5 machines take 5 minutes to make 5 widgets, how long does it take 100 machines to make 100 widgets?", "expected_keyword": "5"},
    {"category": "logic", "question": "Explain 'Object Oriented Programming' in one sentence.", "expected_keyword": "objects"},
    {"category": "logic", "question": "What is a 'stack' data structure?", "expected_keyword": "LIFO"},
    {"category": "logic", "question": "Is the integer 2 prime?", "expected_keyword": "Yes"},
    {"category": "logic", "question": "Simplify: (True OR False) AND True.", "expected_keyword": "True"}
]

def main():
    parser = argparse.ArgumentParser(description="Generate a general-purpose math/econ/logic JSONL eval dataset.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output JSONL path (relative paths are resolved from the project root).",
    )
    args = parser.parse_args()

    output_path = args.output if args.output.is_absolute() else (PROJECT_ROOT / args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for q in questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    
    print(f"Generated {len(questions)} questions at {output_path}")

if __name__ == "__main__":
    main()
