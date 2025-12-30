import memory

def main():
    print("Teacher Mode")
    print("Type a fact to memorize (or 'exit' to quit):")
    
    while True:
        fact = input("\nFact > ")
        if fact.lower() in ["exit", "quit"]:
            break
            
        if fact.strip():
            memory.memorize(fact, source="manual_entry")

if __name__ == "__main__":
    main()