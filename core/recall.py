import memory
import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: python recall.py 'Your query here'")
        return

    query = sys.argv[1]
    print(f"Searching brain for: '{query}'...")
    
    results = memory.recall(query)
    
    print("\n--- FOUND MEMORIES ---")
    for i, fact in enumerate(results):
        print(f"{i+1}. {fact}")

if __name__ == "__main__":
    main()